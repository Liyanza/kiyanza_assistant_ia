"""
Moteur de recommandations d'ajustement de campagne (Kiyanza - extension de
la fonctionnalité 4.4 "Simuler avant de dépenser").

Principe : à partir d'un scénario déjà simulé, on teste des alternatives
réalistes sur les leviers qu'une entreprise peut effectivement changer
(budget, plateforme, tranche d'âge, format créatif — jamais le secteur ou
la taille de l'entreprise, qui sont des faits, pas des choix). Pour chaque
alternative, on relance la prédiction et on compare au scénario de départ.

Si aucune alternative n'apporte un gain significatif, AUCUNE recommandation
n'est renvoyée — conformément à la demande : ne rien proposer si les
résultats sont déjà bons.

La métrique qui décide "qu'est-ce qu'une amélioration" dépend de l'objectif
de la campagne (§6.1 : rester cohérent avec ce que l'entreprise cherche à
obtenir, pas imposer un critère générique).

Convention du projet : importé par les scripts CLI / l'API, ne doit jamais
être exécuté directement.
"""

from simulation_explain import predict_and_explain, predict_only

# Seuil minimal d'amélioration (%) pour qu'une alternative soit jugée
# "recommandable" plutôt que du bruit statistique.
IMPROVEMENT_THRESHOLD_PCT = 10.0

# Nombre maximum de recommandations renvoyées (une par levier au plus,
# pour rester lisible pour un utilisateur non technique).
MAX_RECOMMENDATIONS = 3

# Quelle métrique prioriser selon l'objectif de la campagne (§4.4 : chaque
# recommandation doit être justifiée et cohérente avec le contexte).
# ATTENTION : le ROAS de ce projet dépend presque exclusivement du secteur /
# objectif / segment client (voir generate_augmented_dataset.py), pas du
# budget, de la plateforme, du format ou de l'âge cible. Se fier au SEUL
# ROAS pour juger une alternative de plateforme/budget/format/âge ne
# détecterait donc presque jamais d'amélioration, même sur un scénario
# clairement sous-optimal. On utilise à la place un score composite
# pondérant les 4 métriques, pour que les leviers réellement testés
# (budget, plateforme, âge, format) puissent faire une différence détectable.
OBJECTIVE_METRIC_WEIGHTS = {
    "Sales":               {"roas": 0.5, "ctr_percent": 0.3, "engagement_rate_percent": 0.1, "reach": 0.1},
    "Lead Generation":     {"roas": 0.4, "ctr_percent": 0.4, "engagement_rate_percent": 0.1, "reach": 0.1},
    "App Adoption":        {"roas": 0.4, "ctr_percent": 0.3, "engagement_rate_percent": 0.2, "reach": 0.1},
    "Brand Awareness":     {"reach": 0.6, "engagement_rate_percent": 0.2, "ctr_percent": 0.1, "roas": 0.1},
    "Product Launch":      {"reach": 0.4, "engagement_rate_percent": 0.3, "ctr_percent": 0.2, "roas": 0.1},
    "Customer Engagement": {"engagement_rate_percent": 0.6, "ctr_percent": 0.2, "reach": 0.1, "roas": 0.1},
    "Website Traffic":     {"ctr_percent": 0.6, "engagement_rate_percent": 0.2, "reach": 0.1, "roas": 0.1},
}
DEFAULT_METRIC_WEIGHTS = {"roas": 0.25, "ctr_percent": 0.25, "engagement_rate_percent": 0.25, "reach": 0.25}
# Conservé pour l'affichage ("priority_metric" reste utile à titre indicatif
# dans la réponse), même si la décision repose désormais sur le score composite.
OBJECTIVE_TO_PRIORITY_METRIC = {
    "Sales": "roas",
    "Lead Generation": "roas",
    "App Adoption": "roas",
    "Brand Awareness": "reach",
    "Product Launch": "reach",
    "Customer Engagement": "engagement_rate_percent",
    "Website Traffic": "ctr_percent",
}
DEFAULT_PRIORITY_METRIC = "roas"

# Placements valides par plateforme (cohérence des scénarios alternatifs :
# on ne propose jamais "TikTok" + placement "Search Results", qui n'existe
# pas). Reprend le mapping utilisé lors de la génération du dataset
# (generate_augmented_dataset.py).
PLATFORM_PLACEMENTS = {
    "Facebook": ["Feed", "Stories", "Reels"],
    "Instagram": ["Feed", "Stories", "Reels"],
    "TikTok": ["Feed", "Reels"],
    "YouTube": ["In-Stream Video"],
    "Google Ads": ["Search Results", "Display Network"],
    "Google Display Network": ["Display Network"],
    "Email": ["Feed"],
    "WhatsApp Business": ["Feed"],
}

# Chaque plateforme correspond à un seul canal dans les données
# d'entraînement (vérifié par crosstab : correspondance stricte 1-à-1).
# Indispensable pour ne jamais soumettre au modèle une combinaison
# canal/plateforme qu'il n'a jamais vue (ex. TikTok + Paid Search).
PLATFORM_TO_CHANNEL = {
    "Email": "Email Marketing",
    "Facebook": "Social Media",
    "Google Ads": "Paid Search",
    "Google Display Network": "Display Advertising",
    "Instagram": "Social Media",
    "TikTok": "Social Media",
    "WhatsApp Business": "Messaging",
    "YouTube": "Video",
}

# Valeurs candidates pour chaque levier testable.
CANDIDATE_PLATFORMS = list(PLATFORM_PLACEMENTS.keys())
CANDIDATE_TARGET_AGES = ["18-24", "18-34", "25-34", "25-44", "35-44", "45-54", "All Adults"]
CANDIDATE_CREATIVE_FORMATS = ["Banner", "Carousel", "Image", "Long-form Video", "Short Video", "Story", "Text and Image"]
BUDGET_INCREASE_FACTORS = [1.25, 1.50]

METRIC_LABELS = {
    "reach": "la portée",
    "engagement_rate_percent": "le taux d'engagement",
    "ctr_percent": "le taux de clic",
    "roas": "le retour sur investissement (ROAS)",
}


def get_priority_metric(campaign_objective: str) -> str:
    return OBJECTIVE_TO_PRIORITY_METRIC.get(campaign_objective, DEFAULT_PRIORITY_METRIC)


def get_metric_weights(campaign_objective: str) -> dict:
    return OBJECTIVE_METRIC_WEIGHTS.get(campaign_objective, DEFAULT_METRIC_WEIGHTS)


def composite_improvement_pct(baseline_predictions: dict, alt_predictions: dict, weights: dict) -> float:
    """
    Calcule un score d'amélioration global (%) entre deux jeux de
    prédictions, en pondérant le changement relatif de chaque métrique
    selon les poids définis pour l'objectif de la campagne.
    """
    score = 0.0
    for metric, weight in weights.items():
        baseline_value = baseline_predictions[metric]
        if baseline_value == 0:
            continue
        pct_change = (alt_predictions[metric] - baseline_value) / abs(baseline_value) * 100
        score += weight * pct_change
    return score


def _valid_placement_for_platform(current_placement: str, new_platform: str) -> str:
    """Choisit un placement cohérent avec la nouvelle plateforme testée."""
    valid_options = PLATFORM_PLACEMENTS.get(new_platform, ["Feed"])
    if current_placement in valid_options:
        return current_placement
    return valid_options[0]


def _generate_candidate_alternatives(scenario: dict):
    """
    Génère une liste de scénarios alternatifs, chacun ne modifiant QU'UN
    SEUL levier par rapport au scénario de départ.

    Retourne une liste de tuples (lever, description_valeur, scenario_modifie).
    """
    candidates = []

    # --- Levier : budget ---
    for factor in BUDGET_INCREASE_FACTORS:
        alt = dict(scenario)
        alt["budget_xaf"] = round(scenario["budget_xaf"] * factor)
        candidates.append((
            "budget_xaf",
            f"{alt['budget_xaf']:,.0f} FCFA (+{int((factor - 1) * 100)}%)".replace(",", " "),
            alt,
        ))

    # --- Levier : plateforme ---
    for platform in CANDIDATE_PLATFORMS:
        if platform == scenario["platform"]:
            continue
        alt = dict(scenario)
        alt["platform"] = platform
        alt["channel"] = PLATFORM_TO_CHANNEL.get(platform, scenario["channel"])
        alt["placement"] = _valid_placement_for_platform(scenario["placement"], platform)
        candidates.append(("platform", platform, alt))

    # --- Levier : tranche d'âge cible ---
    for age in CANDIDATE_TARGET_AGES:
        if age == scenario["target_age"]:
            continue
        alt = dict(scenario)
        alt["target_age"] = age
        candidates.append(("target_age", age, alt))

    # --- Levier : format créatif ---
    for fmt in CANDIDATE_CREATIVE_FORMATS:
        if fmt == scenario["creative_format"]:
            continue
        alt = dict(scenario)
        alt["creative_format"] = fmt
        candidates.append(("creative_format", fmt, alt))

    return candidates


def _find_justification(explanations: dict, baseline_predictions: dict, alt_predictions: dict,
                         weights: dict, lever: str, new_value: str) -> str:
    """
    Identifie la métrique la plus impactée par ce changement (parmi celles
    pondérées pour cet objectif), puis cherche une justification concrète
    dans les facteurs explicatifs déjà calculés pour cette métrique — sinon
    retombe sur une phrase générique mentionnant le changement observé.
    """
    pct_changes = {}
    for metric in weights:
        baseline_value = baseline_predictions[metric]
        if baseline_value == 0:
            continue
        pct_changes[metric] = (alt_predictions[metric] - baseline_value) / abs(baseline_value) * 100

    if not pct_changes:
        return f"Cette option améliore les résultats attendus pour ce contexte."

    headline_metric = max(pct_changes, key=lambda m: abs(pct_changes[m]))
    headline_pct = pct_changes[headline_metric]

    for factor in explanations.get(headline_metric, []):
        if factor["feature"] == lever and factor["value"] == new_value:
            return (
                f"{new_value} génère historiquement {abs(factor['lift_pct'])}% "
                f"{'de plus' if factor['lift_pct'] > 0 else 'de moins'} que la moyenne "
                f"sur {METRIC_LABELS.get(headline_metric, headline_metric)} "
                f"(basé sur {factor['n_historique']} campagnes similaires)."
            )

    return (
        f"Cette option améliore {METRIC_LABELS.get(headline_metric, headline_metric)} "
        f"de {headline_pct:+.1f}% par rapport au scénario actuel."
    )


def generate_recommendations(scenario: dict) -> dict:
    """
    Pipeline complet : simule le scénario de départ, teste rapidement les
    alternatives réalistes (prédiction seule, sans explicabilité complète
    pour rester rapide) via un score composite pondéré selon l'objectif,
    puis calcule l'explication détaillée UNIQUEMENT pour les quelques
    recommandations finalement retenues.
    """
    baseline = predict_and_explain(scenario)
    baseline_predictions = baseline["predictions"]
    priority_metric = get_priority_metric(scenario["campaign_objective"])
    weights = get_metric_weights(scenario["campaign_objective"])

    scored_candidates = []
    for lever, value_label, alt_scenario in _generate_candidate_alternatives(scenario):
        alt_predictions = predict_only(alt_scenario)
        composite_pct = composite_improvement_pct(baseline_predictions, alt_predictions, weights)

        if composite_pct >= IMPROVEMENT_THRESHOLD_PCT:
            scored_candidates.append({
                "lever": lever,
                "recommended_value": value_label,
                "improvement_pct": round(composite_pct, 1),
                "alt_scenario": alt_scenario,
                "alt_predictions": alt_predictions,
            })

    # Garde la meilleure alternative par levier (évite de spammer 7
    # variantes de plateforme si plusieurs dépassent le seuil).
    best_per_lever = {}
    for c in scored_candidates:
        current_best = best_per_lever.get(c["lever"])
        if current_best is None or c["improvement_pct"] > current_best["improvement_pct"]:
            best_per_lever[c["lever"]] = c

    top_candidates = sorted(
        best_per_lever.values(), key=lambda c: c["improvement_pct"], reverse=True
    )[:MAX_RECOMMENDATIONS]

    # Explication détaillée calculée seulement pour les finalistes retenus.
    recommendations = []
    for c in top_candidates:
        alt_result = predict_and_explain(c["alt_scenario"])
        recommendations.append({
            "lever": c["lever"],
            "recommended_value": c["recommended_value"],
            "improvement_pct": c["improvement_pct"],
            "predictions": alt_result["predictions"],
            "justification": _find_justification(
                alt_result["explanations"], baseline_predictions, alt_result["predictions"],
                weights, c["lever"], c["recommended_value"]
            ),
        })

    return {
        "baseline_predictions": baseline_predictions,
        "priority_metric": priority_metric,
        "recommendations": recommendations,
        "message": (
            None if recommendations else
            "Les paramètres actuels donnent déjà de bons résultats : aucun "
            "ajustement testé n'apporte d'amélioration significative."
        ),
    }
