"""
Script CLI - Étape 3 du module "Simuler avant de dépenser" (Kiyanza).

Prend un scénario de campagne (paramètres du plan marketing, étape 4.3) et
retourne les 4 prédictions (reach, engagement, ctr, roas) accompagnées des
principaux facteurs qui les expliquent, sous forme de JSON structuré.

Ce script est un outil de test/diagnostic : il permet de vérifier que la
prédiction + l'explicabilité fonctionnent avant de les brancher sur l'API et
la génération de texte en langage naturel (étape 4).

IMPORTANT : à exécuter depuis la racine du projet, après avoir exécuté
07_prepare_simulation_data.py et 08_train_simulation_models.py.

Usage :
    python 09_explain_prediction.py --scenario-file exemples/scenario_1.json

    # Ou directement en ligne de commande :
    python 09_explain_prediction.py \
        --industry "Technology" --company-size Small --city Douala \
        --campaign-objective Sales --campaign-type "Social Media Campaign" \
        --channel "Social Media" --platform Instagram --placement Feed \
        --target-age 18-34 --target-gender All --customer-segment SMEs \
        --creative-format "Short Video" --content-type Promotional \
        --duration-days 30 --budget-xaf 500000
"""

import json
from simulation_explain import predict_and_explain, build_scenario_arg_parser, scenario_from_args


def main():
    parser = build_scenario_arg_parser("Prédiction + explication d'un scénario de campagne Kiyanza")
    args = parser.parse_args()
    scenario = scenario_from_args(args)

    result = predict_and_explain(scenario)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
