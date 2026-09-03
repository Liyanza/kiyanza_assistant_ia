"""
Logique réutilisable pour l'entraînement des modèles de simulation de
campagne (Kiyanza - fonctionnalité 4.4 "Simuler avant de dépenser").

Ce module :
1. Charge train.pkl / test.pkl / feature_schema.json (produits par
   l'étape 1 - simulation_data_prep.py)
2. Entraîne un XGBoost Regressor par cible (reach, engagement_rate_percent,
   ctr_percent, roas)
3. Évalue chaque modèle sur le jeu de test (MAE, RMSE, R²)
4. Journalise les paramètres, métriques et modèles dans MLflow
5. Sauvegarde aussi les modèles localement (joblib) pour un chargement
   rapide par le futur module d'inférence / API de simulation

Convention du projet : ce module est importé par le script CLI numéroté
(08_train_simulation_models.py) et ne doit jamais être exécuté directement.
"""

import os
import json
import joblib
import pandas as pd
import mlflow
import mlflow.xgboost
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

DATA_DIR = "data/simulation"
MODELS_DIR = "models/simulation"

# Hyperparamètres par défaut. Volontairement simples et robustes (pas de
# recherche d'hyperparamètres exhaustive) : contexte hackathon, priorité à
# un pipeline complet et fiable plutôt qu'à la performance maximale.
DEFAULT_PARAMS = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
}


def load_data():
    """Charge les jeux train/test et le schéma de features produits à l'étape 1."""
    train_path = os.path.join(DATA_DIR, "train.pkl")
    test_path = os.path.join(DATA_DIR, "test.pkl")
    schema_path = os.path.join(DATA_DIR, "feature_schema.json")

    for p in (train_path, test_path, schema_path):
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"{p} introuvable. As-tu bien exécuté "
                f"07_prepare_simulation_data.py avant ce script ?"
            )

    train_df = pd.read_pickle(train_path)
    test_df = pd.read_pickle(test_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    return train_df, test_df, schema


def train_one_model(train_df, test_df, feature_columns, target, params):
    """
    Entraîne un XGBRegressor pour une cible donnée, l'évalue sur le test,
    et retourne (modèle, métriques).
    """
    X_train, y_train = train_df[feature_columns], train_df[target]
    X_test, y_test = test_df[feature_columns], test_df[target]

    model = XGBRegressor(**params, objective="reg:squarederror", n_jobs=-1)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    metrics = {
        "mae": float(mean_absolute_error(y_test, y_pred)),
        "rmse": float(mean_squared_error(y_test, y_pred) ** 0.5),
        "r2": float(r2_score(y_test, y_pred)),
        # MAE relatif à la moyenne de la cible : lisible même sans connaître
        # l'échelle (ex. reach compte en centaines de milliers, roas en unités).
        "mae_pct_of_mean": float(mean_absolute_error(y_test, y_pred) / y_test.mean() * 100),
    }

    return model, metrics


def train_all_models(
    mlflow_tracking_uri: str = "sqlite:///mlflow.db",
    experiment_name: str = "kiyanza_simulation_campagne",
    params: dict = None,
):
    """Pipeline complet : entraîne et journalise les 4 modèles de simulation."""

    params = params or DEFAULT_PARAMS

    mlflow.set_tracking_uri(mlflow_tracking_uri)
    mlflow.set_experiment(experiment_name)

    print("[1/3] Chargement des données préparées...")
    train_df, test_df, schema = load_data()
    feature_columns = schema["encoded_feature_columns"]
    target_columns = schema["target_columns"]
    print(f"       -> {len(train_df)} lignes train, {len(test_df)} lignes test, "
          f"{len(feature_columns)} features, {len(target_columns)} cibles.")

    os.makedirs(MODELS_DIR, exist_ok=True)
    all_metrics = {}

    print("[2/3] Entraînement d'un modèle par cible...")
    for target in target_columns:
        print(f"\n   -- Cible : {target} --")
        with mlflow.start_run(run_name=f"xgboost_{target}"):
            mlflow.log_params(params)
            mlflow.log_param("target", target)
            mlflow.log_param("n_features", len(feature_columns))
            mlflow.log_param("n_train_rows", len(train_df))

            model, metrics = train_one_model(train_df, test_df, feature_columns, target, params)

            mlflow.log_metrics(metrics)
            mlflow.xgboost.log_model(model, name="model")

            model_path = os.path.join(MODELS_DIR, f"xgboost_{target}.joblib")
            joblib.dump(model, model_path)

            print(f"       MAE  : {metrics['mae']:.3f}  ({metrics['mae_pct_of_mean']:.1f}% de la moyenne)")
            print(f"       RMSE : {metrics['rmse']:.3f}")
            print(f"       R²   : {metrics['r2']:.3f}")
            print(f"       -> sauvegardé : {model_path}")

            all_metrics[target] = metrics

    print("\n[3/3] Sauvegarde du résumé des métriques...")
    summary_path = os.path.join(MODELS_DIR, "metrics_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, ensure_ascii=False, indent=2)
    print(f"       -> {summary_path}")

    print(f"\nTerminé. Pour explorer les runs MLflow : mlflow ui --backend-store-uri sqlite:///mlflow.db")

    return all_metrics
