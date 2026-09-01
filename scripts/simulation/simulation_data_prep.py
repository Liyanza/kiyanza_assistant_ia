"""
Logique réutilisable pour la préparation des données d'entraînement
du module de simulation de campagne (Kiyanza - fonctionnalité 4.4
"Simuler avant de dépenser").

Ce module :
1. Charge les campagnes historiques (PostgreSQL en production, Excel en mode test)
2. Sélectionne les features "pré-campagne" (connues avant de lancer une campagne)
   et les cibles "post-campagne" (reach, engagement, CTR, ROAS)
3. Encode les variables catégorielles (one-hot) et sauvegarde le schéma d'encodage,
   indispensable pour ré-encoder de la même façon au moment de la prédiction
4. Découpe en train/test et sauvegarde les fichiers prêts pour l'entraînement

Convention du projet : ce module est importé par le script CLI numéroté
(07_prepare_simulation_data.py) et ne doit jamais être exécuté directement.
"""

import os
import json
import pandas as pd
from sklearn.model_selection import train_test_split

# --- Configuration -----------------------------------------------------------

# Features "d'entrée" : connues AVANT le lancement de la campagne.
# Ce sont les champs que le wizard "Créer une campagne" (étapes 4.2 / 4.3 du
# cahier des charges IA) collecte déjà ou peut collecter facilement.
INPUT_FEATURES = [
    "industry",
    "company_size",
    "city",
    "campaign_objective",
    "campaign_type",
    "channel",
    "platform",
    "placement",
    "target_age",
    "target_gender",
    "customer_segment",
    "creative_format",
    "content_type",
    "duration_days",
    "budget_xaf",
]

# Colonnes numériques (pas besoin d'encodage one-hot)
NUMERIC_FEATURES = ["duration_days", "budget_xaf"]

# Colonnes catégorielles (encodage one-hot)
CATEGORICAL_FEATURES = [f for f in INPUT_FEATURES if f not in NUMERIC_FEATURES]

# Cibles à prédire : connues seulement APRES la campagne.
# Correspond à "portée estimée, niveau d'engagement attendu" (§4.4 cahier des
# charges) + CTR et ROAS, essentiels pour une décision "avant de dépenser".
TARGET_COLUMNS = [
    "reach",
    "engagement_rate_percent",
    "ctr_percent",
    "roas",
]

OUTPUT_DIR = "data/simulation"


def load_from_excel(path: str) -> pd.DataFrame:
    """Mode test/dev : charge directement depuis le fichier Excel fourni."""
    return pd.read_excel(path)


def load_from_postgres(connection_string: str, table_name: str = "campaigns") -> pd.DataFrame:
    """
    Mode production : charge les campagnes historiques depuis PostgreSQL.

    connection_string : ex. "postgresql://user:password@localhost:5432/kiyanza"
    table_name : nom de la table créée par 02_load_excel_to_postgres.py
    """
    from sqlalchemy import create_engine

    engine = create_engine(connection_string)
    query = f"SELECT * FROM {table_name}"
    return pd.read_sql(query, engine)


def select_and_clean(df: pd.DataFrame) -> pd.DataFrame:
    """Garde uniquement les colonnes utiles, retire les lignes incomplètes."""
    columns_needed = INPUT_FEATURES + TARGET_COLUMNS
    missing_cols = [c for c in columns_needed if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Colonnes manquantes dans les données source : {missing_cols}. "
            f"Vérifie le nom de la table/des colonnes dans PostgreSQL."
        )

    df = df[columns_needed].copy()

    before = len(df)
    df = df.dropna(subset=columns_needed)
    after = len(df)
    if before != after:
        print(f"[info] {before - after} ligne(s) retirée(s) (valeurs manquantes) sur {before}.")

    return df


def encode_features(df: pd.DataFrame):
    """
    Encode les variables catégorielles en one-hot.

    Retourne le dataframe encodé + la liste des colonnes finales de features
    (le "schéma"). Ce schéma doit être réutilisé tel quel au moment de la
    prédiction en production, sinon les colonnes ne correspondront plus à
    celles vues par le modèle à l'entraînement.
    """
    df_encoded = pd.get_dummies(df, columns=CATEGORICAL_FEATURES, drop_first=False)
    feature_columns = [c for c in df_encoded.columns if c not in TARGET_COLUMNS]
    return df_encoded, feature_columns


def prepare(
    source: str,
    excel_path: str = None,
    connection_string: str = None,
    table_name: str = "campaigns",
    test_size: float = 0.2,
    random_state: int = 42,
):
    """Pipeline complet de préparation des données. Retourne (train_df, test_df, schema)."""

    if source == "excel":
        if not excel_path:
            raise ValueError("--excel-path est requis en mode 'excel'.")
        print(f"[1/5] Chargement depuis Excel : {excel_path}")
        df = load_from_excel(excel_path)
    elif source == "postgres":
        if not connection_string:
            connection_string = os.environ.get("DATABASE_URL")
        if not connection_string:
            raise ValueError(
                "Aucune chaîne de connexion PostgreSQL fournie. "
                "Passe --connection-string ou définis la variable d'environnement DATABASE_URL."
            )
        print(f"[1/5] Chargement depuis PostgreSQL, table '{table_name}'")
        df = load_from_postgres(connection_string, table_name)
    else:
        raise ValueError("source doit être 'excel' ou 'postgres'.")

    print(f"       -> {len(df)} ligne(s) chargée(s).")

    print("[2/5] Sélection des colonnes et nettoyage...")
    df = select_and_clean(df)
    print(f"       -> {len(df)} ligne(s) valide(s) conservée(s).")

    print("[3/5] Encodage des variables catégorielles...")
    df_encoded, feature_columns = encode_features(df)
    print(f"       -> {len(feature_columns)} feature(s) après encodage.")

    print("[4/5] Découpage train / test (80/20)...")
    train_df, test_df = train_test_split(df_encoded, test_size=test_size, random_state=random_state)
    print(f"       -> {len(train_df)} ligne(s) train, {len(test_df)} ligne(s) test.")

    print("[5/5] Sauvegarde des fichiers de sortie...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    train_path = os.path.join(OUTPUT_DIR, "train.parquet")
    test_path = os.path.join(OUTPUT_DIR, "test.parquet")
    schema_path = os.path.join(OUTPUT_DIR, "feature_schema.json")

    train_df.to_parquet(train_path, index=False)
    test_df.to_parquet(test_path, index=False)

    schema = {
        "input_features_raw": INPUT_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "target_columns": TARGET_COLUMNS,
        "encoded_feature_columns": feature_columns,
    }
    with open(schema_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    print(f"       -> {train_path}")
    print(f"       -> {test_path}")
    print(f"       -> {schema_path}")

    return train_df, test_df, schema
