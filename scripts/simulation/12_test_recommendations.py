"""
Script CLI - Teste le moteur de recommandations (étape A de l'extension
"lancer la campagne" / ajustements de paramètres).

Prend un scénario de campagne complet et affiche les recommandations
d'ajustement (budget, plateforme, tranche d'âge, format créatif) qui
amélioreraient significativement les résultats attendus — ou un message
indiquant que le scénario est déjà bon.

IMPORTANT : à exécuter depuis la racine du projet, après les étapes 1 et 2
(07, 08).

Usage :
    python scripts/simulation/12_test_recommendations.py \
        --industry "Technology" --company-size Small --city Douala \
        --campaign-objective Sales --campaign-type "Social Media Campaign" \
        --channel "Display Advertising" --platform "Google Display Network" --placement "Display Network" \
        --target-age 45-54 --target-gender All --customer-segment "Mass Market" \
        --creative-format Banner --content-type Promotional \
        --duration-days 30 --budget-xaf 500000
"""

import json
from simulation_explain import build_scenario_arg_parser, scenario_from_args
from campaign_recommendations import generate_recommendations


def main():
    parser = build_scenario_arg_parser("Teste le moteur de recommandations Kiyanza")
    args = parser.parse_args()
    scenario = scenario_from_args(args)

    result = generate_recommendations(scenario)

    print("=" * 70)
    print(f"Métrique prioritaire pour cet objectif : {result['priority_metric']}")
    print(f"Prédictions de départ : {result['baseline_predictions']}")
    print("=" * 70)

    if not result["recommendations"]:
        print(result["message"])
    else:
        for i, rec in enumerate(result["recommendations"], 1):
            print(f"\n{i}. Levier : {rec['lever']} -> {rec['recommended_value']}")
            print(f"   Amélioration estimée (score composite) : +{rec['improvement_pct']}%")
            print(f"   Nouvelles prédictions : {rec['predictions']}")
            print(f"   Justification : {rec['justification']}")

    print("\nJSON complet :")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
