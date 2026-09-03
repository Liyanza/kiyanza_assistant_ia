"""
Couche d'explicabilité pour le module de simulation de campagne (Kiyanza -
fonctionnalité 4.4 "Simuler avant de dépenser").

Approche volontairement simple ("rules engine"), pas de SHAP/LIME (prévu en
Phase 2 selon le cahier des charges IA) : pour chaque prédiction, on compare
le scénario proposé aux moyennes historiques par catégorie (canal, secteur,
format créatif...) afin d'identifier les facteurs qui tirent le résultat vers
le haut ou vers le bas, et de quelle ampleur.

Ce module :
1. Charge les 4 modèles entraînés (étape 2) + le schéma de features (étape 1)
2. Encode un scénario de campagne (dict) avec le même schéma qu'à l'entraînement
3. Prédit les 4 métriques (reach, engagement, ctr, roas)
4. Calcule, pour chaque métrique, les facteurs catégoriels qui expliquent le
   plus l'écart par rapport à la moyenne générale du secteur

Convention du projet : importé par 09_explain_prediction.py, ne doit jamais
être exécuté directement.
"""

import argparse
import json
from functools import lru_cache

import joblib
import pandas as pd

DATA_DIR = "data/simulation"
MODELS_DIR = "models/simulation"

TOP_N_FACTORS = 3  # nombre de facteurs explicatifs remontés par métrique


def load_schema():
    with open(f"{DATA_DIR}/feature_schema.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_models(target_columns):
    models = {}
    for target in target_columns:
        path = f"{MODELS_DIR}/xgboost_{target}.joblib"
        try:
            models[target] = joblib.load(path)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"{path} introuvable. As-tu bien exécuté "
                f"08_train_simulation_models.py avant ce script ?"
            )
    return models


def load_train_data():
    path = f"{DATA_DIR}/train.pkl"
    try:
        return pd.read_pickle(path)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"{path} introuvable. As-tu bien exécuté "
            f"07_prepare_simulation_data.py avant ce script ?"
        )


def encode_scenario(scenario: dict, schema: dict):
    """
    Transforme un scénario de campagne (dict de valeurs brutes, ex.
    {"channel": "Social Media", "budget_xaf": 500000, ...}) en une ligne de
    features encodées, avec EXACTEMENT les mêmes colonnes que celles vues à
    l'entraînement (schema["encoded_feature_columns"]).

    Toute valeur catégorielle absente du scénario, ou jamais vue à
    l'entraînement, se traduit simplement par des colonnes à 0 (le modèle
    l'ignore, ce qui revient à ne pas privilégier cette catégorie).
    """
    row = {col: 0 for col in schema["encoded_feature_columns"]}

    for feature in schema["numeric_features"]:
        if feature not in scenario:
            raise ValueError(f"Champ obligatoire manquant dans le scénario : {feature}")
        row[feature] = scenario[feature]

    unknown_categories = []
    for feature in schema["categorical_features"]:
        if feature not in scenario:
            raise ValueError(f"Champ obligatoire manquant dans le scénario : {feature}")
        dummy_col = f"{feature}_{scenario[feature]}"
        if dummy_col in row:
            row[dummy_col] = 1
        else:
            unknown_categories.append((feature, scenario[feature]))

    encoded = pd.DataFrame([row])[schema["encoded_feature_columns"]]
    return encoded, unknown_categories


def compute_categorical_lift(train_df: pd.DataFrame, target: str, scenario_dummies: list):
    """
    Pour chaque (feature, valeur, colonne encodée) activée par le scénario
    (ex. ("channel", "Social Media", "channel_Social Media")), calcule
    l'écart entre la moyenne du target pour cette catégorie et la moyenne
    générale du dataset.

    Retourne une liste de facteurs triés par ampleur d'écart décroissante.
    """
    overall_mean = train_df[target].mean()
    factors = []

    for feature_name, value, dummy_col in scenario_dummies:
        if dummy_col not in train_df.columns:
            continue
        mask = train_df[dummy_col] == 1
        n = int(mask.sum())
        if n < 30:  # trop peu d'exemples historiques pour être fiable
            continue
        group_mean = train_df.loc[mask, target].mean()
        lift = group_mean - overall_mean
        factors.append({
            "feature": feature_name,
            "value": value,
            "group_mean": round(float(group_mean), 3),
            "overall_mean": round(float(overall_mean), 3),
            "lift": round(float(lift), 3),
            "lift_pct": round(float(lift / overall_mean * 100), 1) if overall_mean else 0.0,
            "direction": "hausse" if lift > 0 else "baisse",
            "n_historique": n,
        })

    factors.sort(key=lambda f: abs(f["lift_pct"]), reverse=True)
    return factors[:TOP_N_FACTORS]


@lru_cache(maxsize=1)
def load_artifacts():
    """
    Charge le schéma, les 4 modèles et les données d'entraînement UNE SEULE
    FOIS par processus (grâce à lru_cache), puis les garde en mémoire.

    Un script CLI (une seule exécution) ne voit aucune différence de
    comportement. Une API qui reste allumée (étape 5) bénéficie en revanche
    d'un gain de temps considérable : sans ce cache, chaque requête HTTP
    rechargerait les 4 modèles XGBoost et 16 000 lignes de données
    d'entraînement depuis le disque, ce qui violerait l'exigence de
    performance du cahier des charges (§6.2 : réponse en quelques secondes).
    """
    schema = load_schema()
    models = load_models(schema["target_columns"])
    train_df = load_train_data()
    return schema, models, train_df


def predict_and_explain(scenario: dict):
    """
    Pipeline complet : encode le scénario, prédit les 4 métriques, explique
    chaque prédiction par ses principaux facteurs catégoriels.
    """
    schema, models, train_df = load_artifacts()

    encoded, unknown_categories = encode_scenario(scenario, schema)

    scenario_dummies = [
        (feature, scenario[feature], f"{feature}_{scenario[feature]}")
        for feature in schema["categorical_features"]
        if feature in scenario
    ]

    result = {"predictions": {}, "explanations": {}, "warnings": []}

    for feature, value in unknown_categories:
        result["warnings"].append(
            f"Valeur inconnue pour '{feature}' : '{value}' n'a pas été vue dans les "
            f"données d'entraînement. La prédiction ignore ce paramètre."
        )

    for target in schema["target_columns"]:
        prediction = float(models[target].predict(encoded)[0])
        result["predictions"][target] = round(prediction, 3)
        result["explanations"][target] = compute_categorical_lift(train_df, target, scenario_dummies)

    return result


# ---------------------------------------------------------------------------
# Aide à la construction d'un scénario de campagne en ligne de commande.
# Partagée par 09_explain_prediction.py et 10_generate_simulation_text.py,
# pour éviter de dupliquer la même liste d'arguments dans les deux scripts.
# ---------------------------------------------------------------------------

CLI_TO_FEATURE = {
    "industry": "industry",
    "company_size": "company_size",
    "city": "city",
    "campaign_objective": "campaign_objective",
    "campaign_type": "campaign_type",
    "channel": "channel",
    "platform": "platform",
    "placement": "placement",
    "target_age": "target_age",
    "target_gender": "target_gender",
    "customer_segment": "customer_segment",
    "creative_format": "creative_format",
    "content_type": "content_type",
    "duration_days": "duration_days",
    "budget_xaf": "budget_xaf",
}


def build_scenario_arg_parser(description: str) -> argparse.ArgumentParser:
    """Construit un ArgumentParser avec un argument par champ du scénario,
    plus --scenario-file comme alternative (fichier JSON)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--scenario-file", default=None,
        help="Chemin vers un fichier JSON contenant le scénario complet",
    )
    for cli_name in CLI_TO_FEATURE:
        arg_name = f"--{cli_name.replace('_', '-')}"
        if cli_name == "duration_days":
            parser.add_argument(arg_name, type=int, default=None)
        elif cli_name == "budget_xaf":
            parser.add_argument(arg_name, type=float, default=None)
        else:
            parser.add_argument(arg_name, default=None)
    return parser


def scenario_from_args(args) -> dict:
    """Construit le dict de scénario soit depuis --scenario-file, soit
    depuis les arguments individuels."""
    if args.scenario_file:
        with open(args.scenario_file, "r", encoding="utf-8") as f:
            return json.load(f)

    scenario = {}
    for cli_name, feature_name in CLI_TO_FEATURE.items():
        value = getattr(args, cli_name)
        if value is None:
            raise ValueError(
                f"--{cli_name.replace('_', '-')} est requis (ou utilise --scenario-file)."
            )
        scenario[feature_name] = value
    return scenario
