"""
Script CLI - Étape 4 du module "Simuler avant de dépenser" (Kiyanza).

Prend un scénario de campagne et affiche l'estimation finale rédigée en
français clair par le LLM local (Ollama), avec la mention obligatoire qu'il
s'agit d'une estimation et non d'une garantie.

Prérequis : Ollama doit être lancé (comme pour le chatbot), avec le modèle
llama3.2 disponible.

IMPORTANT : à exécuter depuis la racine du projet, après les étapes 1, 2 et 3
(07, 08, 09).

Usage :
    python 10_generate_simulation_text.py \
        --industry "Technology" --company-size Small --city Douala \
        --campaign-objective Sales --campaign-type "Social Media Campaign" \
        --channel "Social Media" --platform Instagram --placement Feed \
        --target-age 18-34 --target-gender All --customer-segment SMEs \
        --creative-format "Short Video" --content-type Promotional \
        --duration-days 30 --budget-xaf 500000

    # Ou depuis un fichier JSON :
    python 10_generate_simulation_text.py --scenario-file exemples/scenario_1.json

    # Pour aussi afficher les données structurées (prédictions, facteurs) :
    python 10_generate_simulation_text.py --scenario-file ... --show-json
"""

import json
from simulation_explain import build_scenario_arg_parser, scenario_from_args
from simulation_text import generate_simulation_text


def main():
    parser = build_scenario_arg_parser("Génère l'estimation de campagne en français clair (Kiyanza)")
    parser.add_argument("--show-json", action="store_true",
                         help="Affiche aussi les prédictions et facteurs bruts en JSON")
    args = parser.parse_args()

    scenario = scenario_from_args(args)
    result = generate_simulation_text(scenario)

    print("=" * 70)
    print(result["text"])
    print("=" * 70)

    if args.show_json:
        print("\nDonnées structurées sous-jacentes :")
        print(json.dumps(
            {k: v for k, v in result.items() if k != "text"},
            ensure_ascii=False, indent=2,
        ))


if __name__ == "__main__":
    main()
