"""
Script CLI - Étape 1 du module "Simuler avant de dépenser" (Kiyanza).

Prépare les données historiques de campagnes pour l'entraînement des
modèles de simulation (reach, engagement, CTR, ROAS).

IMPORTANT : à exécuter depuis la racine du projet (pas depuis scripts/),
comme les autres scripts numérotés du pipeline (convention déjà en place
pour 01_extract_and_chunk_text.py, 02_load_excel_to_postgres.py, etc.).

Usage :
    # Mode test rapide, directement à partir du fichier Excel :
    python 07_prepare_simulation_data.py --source excel --excel-path chemin/vers/dataset.xlsx

    # Mode production, depuis PostgreSQL (table "campaigns" par défaut) :
    python 07_prepare_simulation_data.py --source postgres --table-name campaigns
"""

import argparse
from simulation_data_prep import prepare


def main():
    parser = argparse.ArgumentParser(description="Préparation des données de simulation Kiyanza")
    parser.add_argument(
        "--source", choices=["excel", "postgres"], default="postgres",
        help="Source des données (défaut: postgres)",
    )
    parser.add_argument(
        "--excel-path", default=None,
        help="Chemin du fichier Excel (requis si --source excel)",
    )
    parser.add_argument(
        "--connection-string", default=None,
        help="Chaîne de connexion PostgreSQL (sinon variable d'environnement DATABASE_URL)",
    )
    parser.add_argument(
        "--table-name", default="campaigns",
        help="Nom de la table PostgreSQL contenant les campagnes historiques (défaut: campaigns)",
    )
    parser.add_argument(
        "--test-size", type=float, default=0.2,
        help="Proportion des données réservée au test (défaut: 0.2)",
    )
    args = parser.parse_args()

    prepare(
        source=args.source,
        excel_path=args.excel_path,
        connection_string=args.connection_string,
        table_name=args.table_name,
        test_size=args.test_size,
    )


if __name__ == "__main__":
    main()
