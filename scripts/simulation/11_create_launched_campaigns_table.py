"""
Script CLI - Crée la table PostgreSQL launched_campaigns, qui enregistrera
les campagnes réellement lancées par les utilisateurs (distincte de la
table campaigns, qui contient les données d'entraînement du modèle).

À exécuter UNE SEULE FOIS (sans danger de le relancer, la table n'est créée
que si elle n'existe pas déjà).

IMPORTANT : à exécuter depuis la racine du projet, avec un fichier .env
rempli (comme pour 02_load_excel_to_postgres.py).

Usage :
    python scripts/simulation/11_create_launched_campaigns_table.py
"""

from campaign_launch import create_table, TABLE_NAME


def main():
    print(f"Création de la table '{TABLE_NAME}' si elle n'existe pas déjà...")
    create_table()
    print("Terminé.")


if __name__ == "__main__":
    main()
