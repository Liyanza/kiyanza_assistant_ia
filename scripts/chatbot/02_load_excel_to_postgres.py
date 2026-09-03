"""
Etape 2 : charger le fichier Excel des campagnes (20 000 lignes) dans
une table PostgreSQL, pour pouvoir l'interroger plus tard en SQL.

Prerequis :
    - PostgreSQL installe et lance
    - Une base de donnees creee (ex: CREATE DATABASE kiyanza;)
    - Un fichier .env rempli (copie de .env.example)

Usage :
    python scripts/02_load_excel_to_postgres.py
"""

import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

# --- Config -------------------------------------------------------------
EXCEL_PATH = Path("data/kiyanza_cameroon_pme_marketing_20k_v3.xlsx")
SHEET_NAME = "PME_Marketing_Dataset"
TABLE_NAME = "campaigns"

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def get_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoyage minimal avant chargement en base."""
    # Normalise les noms de colonnes (deja propres ici, mais on securise)
    df.columns = [c.strip().lower() for c in df.columns]

    # Remplace les "N/A" textuels par de vrais NaN (pandas/SQL les geront comme NULL)
    df = df.replace({"N/A": None, "None": None})

    # Convertit la colonne de date si presente
    if "start_date" in df.columns:
        df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")

    return df


def main():
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(f"Place ton fichier Excel ici : {EXCEL_PATH.resolve()}")

    print("Lecture du fichier Excel...")
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
    print(f"{len(df)} lignes, {len(df.columns)} colonnes chargees depuis Excel.")

    df = clean_dataframe(df)

    engine = get_engine()

    print(f"Ecriture dans la table PostgreSQL '{TABLE_NAME}'...")
    df.to_sql(
        TABLE_NAME,
        engine,
        if_exists="replace",   # remplace la table si elle existe deja
        index=False,
        chunksize=1000,        # insertion par lots pour eviter de saturer la memoire
        method="multi",
    )

    print("Termine. Verification rapide :")
    with engine.connect() as conn:
        count = conn.exec_driver_sql(f"SELECT COUNT(*) FROM {TABLE_NAME}").scalar()
        print(f"-> {count} lignes dans la table '{TABLE_NAME}'.")


if __name__ == "__main__":
    main()
