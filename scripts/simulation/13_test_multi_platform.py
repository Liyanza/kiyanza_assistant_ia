"""
Script CLI - Teste le générateur de scénarios multi-plateformes (étape B).

Prend un scénario de base (sans plateforme/canal/placement/budget, qui
varient par plateforme testée), une liste de plateformes envisagées et un
budget total, puis affiche les 3 répartitions candidates et celle
recommandée.

IMPORTANT : à exécuter depuis la racine du projet, après les étapes 1 et 2
(07, 08).

Usage :
    python scripts/simulation/13_test_multi_platform.py \
        --industry "Technology" --company-size Small --city Douala \
        --campaign-objective Sales --campaign-type "Social Media Campaign" \
        --target-age 18-34 --target-gender All --customer-segment SMEs \
        --creative-format "Short Video" --content-type Promotional \
        --duration-days 30 \
        --platforms "Facebook,Instagram,TikTok" --total-budget-xaf 500000
"""

import argparse
import json
from platform_budget_scenarios import generate_multi_platform_scenarios


def main():
    parser = argparse.ArgumentParser(description="Teste les scénarios multi-plateformes Kiyanza")
    parser.add_argument("--industry", required=True)
    parser.add_argument("--company-size", required=True)
    parser.add_argument("--city", required=True)
    parser.add_argument("--campaign-objective", required=True)
    parser.add_argument("--campaign-type", required=True)
    parser.add_argument("--target-age", required=True)
    parser.add_argument("--target-gender", required=True)
    parser.add_argument("--customer-segment", required=True)
    parser.add_argument("--creative-format", required=True)
    parser.add_argument("--content-type", required=True)
    parser.add_argument("--duration-days", type=int, required=True)
    parser.add_argument("--platforms", required=True, help="Liste séparée par des virgules, ex: Facebook,Instagram,TikTok")
    parser.add_argument("--total-budget-xaf", type=float, required=True)
    args = parser.parse_args()

    base_scenario = {
        "industry": args.industry,
        "company_size": args.company_size,
        "city": args.city,
        "campaign_objective": args.campaign_objective,
        "campaign_type": args.campaign_type,
        "target_age": args.target_age,
        "target_gender": args.target_gender,
        "customer_segment": args.customer_segment,
        "creative_format": args.creative_format,
        "content_type": args.content_type,
        "duration_days": args.duration_days,
    }
    platforms = [p.strip() for p in args.platforms.split(",")]

    result = generate_multi_platform_scenarios(base_scenario, platforms, args.total_budget_xaf)

    print("=" * 70)
    print(f"Métrique prioritaire pour cet objectif : {result['priority_metric']}")
    print("=" * 70)

    for s in result["scenarios"]:
        marker = "  <-- RECOMMANDÉ" if s["is_recommended"] else ""
        print(f"\n{s['label']}{marker}")
        print(f"   Répartition du budget : {s['budget_split']}")
        print(f"   Score vs équitable : {s['score_vs_equitable']:+.1f}%")
        print(f"   Prédictions globales : {s['aggregated_predictions']}")

    print("\nJSON complet :")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
