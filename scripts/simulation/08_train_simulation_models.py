"""
Script CLI - Étape 2 du module "Simuler avant de dépenser" (Kiyanza).

Entraîne 4 modèles XGBoost Regressor (un par cible : reach,
engagement_rate_percent, ctr_percent, roas) à partir des données préparées
par 07_prepare_simulation_data.py, évalue leur précision sur le jeu de test,
et journalise le tout dans MLflow.

IMPORTANT : à exécuter depuis la racine du projet, après avoir exécuté
07_prepare_simulation_data.py.

Usage :
    python 08_train_simulation_models.py

    # Avec des hyperparamètres personnalisés :
    python 08_train_simulation_models.py --n-estimators 500 --max-depth 6

    # Pour explorer les résultats ensuite dans l'interface MLflow :
    mlflow ui --backend-store-uri sqlite:///mlflow.db
"""

import argparse
from simulation_train import train_all_models, DEFAULT_PARAMS


def main():
    parser = argparse.ArgumentParser(description="Entraînement des modèles de simulation Kiyanza")
    parser.add_argument("--mlflow-tracking-uri", default="sqlite:///mlflow.db",
                         help="URI de suivi MLflow (défaut: sqlite:///mlflow.db, local)")
    parser.add_argument("--experiment-name", default="kiyanza_simulation_campagne",
                         help="Nom de l'expérience MLflow")
    parser.add_argument("--n-estimators", type=int, default=DEFAULT_PARAMS["n_estimators"])
    parser.add_argument("--max-depth", type=int, default=DEFAULT_PARAMS["max_depth"])
    parser.add_argument("--learning-rate", type=float, default=DEFAULT_PARAMS["learning_rate"])
    args = parser.parse_args()

    params = dict(DEFAULT_PARAMS)
    params.update({
        "n_estimators": args.n_estimators,
        "max_depth": args.max_depth,
        "learning_rate": args.learning_rate,
    })

    train_all_models(
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        experiment_name=args.experiment_name,
        params=params,
    )


if __name__ == "__main__":
    main()
