"""
Logique reutilisable de l'outil "text-to-SQL". Transforme une question en
langage naturel en requete SQL, l'execute sur la table 'campaigns', et
renvoie le resultat.

Importe par :
    - scripts/04_text_to_sql.py (usage en ligne de commande, pour tester)
    - scripts/06_chatbot.py (chatbot final)
"""

import os
import re

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

from llm_client import ask_llm

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

TABLE_NAME = "campaigns"

SQL_SYSTEM_PROMPT = """Tu es un generateur de requetes SQL PostgreSQL.
Tu recois une question en francais sur des donnees de campagnes marketing,
et le schema de la table disponible.

Regles strictes :
- Reponds UNIQUEMENT avec la requete SQL, sans explication, sans markdown,
  sans backticks.
- Utilise UNIQUEMENT la table et les colonnes fournies dans le schema.
- Genere UNIQUEMENT des requetes SELECT (jamais INSERT, UPDATE, DELETE,
  DROP, ALTER, ou toute autre commande de modification).
- Si la question ne peut pas etre traduite en requete SQL pertinente avec
  le schema fourni, reponds exactement : NO_QUERY
"""


def get_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


def get_table_schema(engine) -> str:
    """Introspecte la table campaigns et renvoie une description du schema."""
    inspector = inspect(engine)
    columns = inspector.get_columns(TABLE_NAME)
    lines = [f"Table '{TABLE_NAME}' :"]
    for col in columns:
        lines.append(f"  - {col['name']} ({col['type']})")
    return "\n".join(lines)


def clean_sql(raw_sql: str) -> str:
    """Retire d'eventuels backticks/markdown que le modele aurait ajoutes."""
    cleaned = raw_sql.strip()
    cleaned = re.sub(r"^```sql", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^```", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def is_safe_select(sql: str) -> bool:
    """Verifie que la requete est bien un SELECT, sans mot-cle dangereux."""
    normalized = sql.strip().lower()
    if not normalized.startswith("select"):
        return False
    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate", "grant", ";--"]
    return not any(word in normalized for word in forbidden)


def answer_with_sql(question: str):
    """
    Pipeline complet : question en langage naturel -> SQL -> execution.
    Renvoie (dataframe_resultat_ou_None, requete_sql_generee).
    """
    engine = get_engine()
    schema = get_table_schema(engine)

    user_message = f"Schema disponible :\n{schema}\n\nQuestion : {question}"
    raw_sql = ask_llm(SQL_SYSTEM_PROMPT, user_message, temperature=0.0)
    sql_query = clean_sql(raw_sql)

    if sql_query == "NO_QUERY" or not is_safe_select(sql_query):
        return None, sql_query

    try:
        with engine.connect() as conn:
            result_df = pd.read_sql(sql_query, conn)
        return result_df, sql_query
    except Exception as e:
        print(f"[Erreur SQL] {e}")
        return None, sql_query
