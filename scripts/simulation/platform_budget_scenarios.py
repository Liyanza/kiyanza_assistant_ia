"""
Génération de scénarios de répartition budgétaire sur plusieurs plateformes
(Kiyanza - extension de la fonctionnalité 4.4 "Simuler avant de dépenser").

Principe : l'utilisateur donne un budget total et une liste de plateformes
envisagées (ex. Facebook, Instagram, TikTok). On génère 3 répartitions
candidates du budget entre ces plateformes, on simule chacune, on agrège
les résultats par plateforme en une prédiction globale, et on indique quelle
répartition est recommandée.

Les 3 répartitions testées :
    1. Équitable       : le budget est divisé également entre les plateformes
    2. Pondérée ROAS    : plus de budget vers les plateformes qui performent
                          historiquement le mieux sur le retour sur investissement
    3. Pondérée portée  : plus de budget vers les plateformes qui touchent
                          historiquement le plus de monde

Le scénario "recommandé" est celui dont le score composite (pondéré selon
l'objectif de la campagne, voir campaign_recommendations.py) est le plus
élevé par rapport à la répartition équitable prise comme référence — même
logique et même fonction de scoring que le moteur de recommandations, pour
rester cohérent.

Convention du projet : importé par l'API, ne doit jamais être exécuté
directement.
"""

from simulation_explain import predict_only, load_artifacts
from campaign_recommendations import (
    get_metric_weights,
    get_priority_metric,
    composite_improvement_pct,
    PLATFORM_PLACEMENTS,
    PLATFORM_TO_CHANNEL,
)

MIN_PLATFORMS = 2
MAX_PLATFORMS = 6

STRATEGY_LABELS = {
    "equitable": "Répartition équitable",
    "ctr_weighted": "Répartition pondérée taux de clic",
    "engagement_weighted": "Répartition pondérée engagement",
}


def _valid_placement_for_platform(platform: str, preferred_placement: str = None) -> str:
    valid_options = PLATFORM_PLACEMENTS.get(platform, ["Feed"])
    if preferred_placement in valid_options:
        return preferred_placement
    return valid_options[0]


def _get_platform_benchmark(train_df, metric: str, platform: str) -> float:
    """Moyenne historique d'une métrique pour une plateforme donnée,
    tous scénarios confondus (sert uniquement à PONDÉRER la répartition
    du budget, pas à prédire — la prédiction fine vient ensuite du modèle
    XGBoost pour le scénario complet)."""
    dummy_col = f"platform_{platform}"
    if dummy_col not in train_df.columns:
        return 0.0
    mask = train_df[dummy_col] == 1
    if mask.sum() < 30:
        return 0.0
    return float(train_df.loc[mask, metric].mean())


def _compute_budget_split(platforms: list, total_budget_xaf: float, strategy: str, train_df) -> dict:
    """
    Retourne {plateforme: budget_alloué} pour une stratégie donnée.

    NOTE IMPORTANTE : on pondère par CTR et engagement, pas par reach/ROAS.
    Vérification empirique sur le dataset d'entraînement : reach et ROAS ne
    varient quasiment pas selon la plateforme (moins de 3% d'écart entre
    plateformes, essentiellement du bruit), alors que CTR (1.6 à 5.3) et
    engagement (4.1 à 9.8) varient réellement. Pondérer par reach/ROAS
    donnerait des répartitions quasi identiques à l'équitable, sans valeur
    ajoutée réelle pour l'utilisateur.
    """
    if strategy == "equitable":
        share = 1.0 / len(platforms)
        return {p: round(total_budget_xaf * share) for p in platforms}

    metric = "ctr_percent" if strategy == "ctr_weighted" else "engagement_rate_percent"
    benchmarks = {p: max(_get_platform_benchmark(train_df, metric, p), 0.0) for p in platforms}
    total_benchmark = sum(benchmarks.values())

    if total_benchmark == 0:
        share = 1.0 / len(platforms)
        return {p: round(total_budget_xaf * share) for p in platforms}

    return {
        p: round(total_budget_xaf * (benchmarks[p] / total_benchmark))
        for p in platforms
    }


def _aggregate_platform_predictions(platform_predictions: dict, budget_split: dict) -> dict:
    """
    Combine les prédictions individuelles de chaque plateforme en une
    estimation globale pour la campagne multi-plateformes :
        - reach : somme (on additionne les personnes touchées sur chaque plateforme)
        - engagement : moyenne pondérée par la portée de chaque plateforme
        - ctr / roas : moyenne pondérée par le budget de chaque plateforme
          (méthodologie standard pour un ROAS/CTR "consolidé")
    """
    total_budget = sum(budget_split.values())
    total_reach = sum(pred["reach"] for pred in platform_predictions.values())

    if total_reach > 0:
        engagement = sum(
            pred["reach"] * pred["engagement_rate_percent"] for pred in platform_predictions.values()
        ) / total_reach
    else:
        engagement = 0.0

    if total_budget > 0:
        ctr = sum(
            budget_split[p] * platform_predictions[p]["ctr_percent"] for p in platform_predictions
        ) / total_budget
        roas = sum(
            budget_split[p] * platform_predictions[p]["roas"] for p in platform_predictions
        ) / total_budget
    else:
        ctr = 0.0
        roas = 0.0

    return {
        "reach": round(total_reach, 3),
        "engagement_rate_percent": round(engagement, 3),
        "ctr_percent": round(ctr, 3),
        "roas": round(roas, 3),
    }


def _simulate_strategy(base_scenario: dict, platforms: list, budget_split: dict) -> dict:
    """Simule chaque tranche de plateforme puis agrège le résultat global."""
    platform_predictions = {}
    for platform in platforms:
        sub_scenario = dict(base_scenario)
        sub_scenario["platform"] = platform
        sub_scenario["channel"] = PLATFORM_TO_CHANNEL.get(platform, base_scenario.get("channel"))
        sub_scenario["placement"] = _valid_placement_for_platform(
            platform, base_scenario.get("placement")
        )
        sub_scenario["budget_xaf"] = budget_split[platform]
        platform_predictions[platform] = predict_only(sub_scenario)

    aggregated = _aggregate_platform_predictions(platform_predictions, budget_split)

    return {
        "budget_split": budget_split,
        "per_platform_predictions": platform_predictions,
        "aggregated_predictions": aggregated,
    }


def generate_multi_platform_scenarios(base_scenario: dict, platforms: list, total_budget_xaf: float) -> dict:
    """
    Pipeline complet : génère et compare les 3 répartitions budgétaires
    candidates entre les plateformes proposées.

    base_scenario : le scénario habituel (industry, company_size, city,
        campaign_objective, ..., target_age, creative_format, content_type,
        duration_days). Les champs platform/placement/budget_xaf sont
        ignorés s'ils sont présents (ils sont recalculés par plateforme).
    platforms : liste des plateformes envisagées (2 à 6).
    total_budget_xaf : budget total à répartir entre ces plateformes.
    """
    if len(platforms) < MIN_PLATFORMS:
        raise ValueError(f"Il faut au moins {MIN_PLATFORMS} plateformes pour comparer des répartitions.")
    if len(platforms) > MAX_PLATFORMS:
        raise ValueError(f"Maximum {MAX_PLATFORMS} plateformes à la fois.")

    _, _, train_df = load_artifacts()

    strategies_results = {}
    for strategy in ("equitable", "ctr_weighted", "engagement_weighted"):
        budget_split = _compute_budget_split(platforms, total_budget_xaf, strategy, train_df)
        strategies_results[strategy] = _simulate_strategy(base_scenario, platforms, budget_split)

    baseline_predictions = strategies_results["equitable"]["aggregated_predictions"]
    weights = get_metric_weights(base_scenario["campaign_objective"])

    scores = {"equitable": 0.0}
    for strategy in ("ctr_weighted", "engagement_weighted"):
        scores[strategy] = composite_improvement_pct(
            baseline_predictions, strategies_results[strategy]["aggregated_predictions"], weights
        )

    recommended_strategy = max(scores, key=scores.get)

    scenarios = []
    for strategy in ("equitable", "ctr_weighted", "engagement_weighted"):
        scenarios.append({
            "strategy": strategy,
            "label": STRATEGY_LABELS[strategy],
            "is_recommended": strategy == recommended_strategy,
            "score_vs_equitable": round(scores[strategy], 1),
            "budget_split": strategies_results[strategy]["budget_split"],
            "per_platform_predictions": strategies_results[strategy]["per_platform_predictions"],
            "aggregated_predictions": strategies_results[strategy]["aggregated_predictions"],
        })

    return {
        "priority_metric": get_priority_metric(base_scenario["campaign_objective"]),
        "scenarios": scenarios,
        "recommended_strategy": recommended_strategy,
    }
