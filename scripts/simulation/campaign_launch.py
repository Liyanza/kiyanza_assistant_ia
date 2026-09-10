"""
Enregistrement des campagnes réellement lancées par l'utilisateur, après
validation de la simulation (Kiyanza - suite de la fonctionnalité 4.4
"Simuler avant de dépenser").

Contrairement aux modules précédents (07 à 10), qui sont sans état (ils
calculent et renvoient un résultat sans rien conserver), ce module ÉCRIT en
base de données : il enregistre les campagnes que l'utilisateur a
explicitement décidé de lancer, avec un instantané de la simulation au
moment du lancement.

Pourquoi conserver la simulation au moment du lancement : la future brique
4.5 "Analyse des performances" devra comparer les résultats RÉELS d'une
campagne à ce qui avait été PRÉVU. Sans cet instantané, cette comparaison
serait impossible une fois que le modèle de simulation aura évolué.

Conformité §6.6 du cahier des charges (Supervision humaine) : ce module
n'enregistre que ce que l'utilisateur a explicitement validé en cliquant sur
"Lancer la campagne" — l'IA ne décide jamais elle-même de lancer une
campagne.

IMPORTANT (à corriger dès que l'information sera connue) : le champ
tenant_id est actuellement optionnel, en attendant de savoir si un système
d'authentification / gestion des entreprises existe déjà côté backend
(Baudouin). Une fois confirmé, il faudra :
  1. Rendre tenant_id obligatoire dans LaunchCampaignRequest (simulation_api.py)
  2. Ajouter une contrainte NOT NULL sur la colonne tenant_id ci-dessous
  3. Vérifier l'isolation multi-tenant (un tenant ne doit jamais voir les
     campagnes d'un autre), comme prévu dans l'architecture du projet.
"""

import os
import uuid
from datetime import datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

TABLE_NAME = "launched_campaigns"

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


def get_engine():
    url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(url)


CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id SERIAL PRIMARY KEY,
    campaign_id VARCHAR(32) UNIQUE NOT NULL,
    tenant_id VARCHAR(64),                   -- optionnel pour l'instant, voir docstring
    campaign_name VARCHAR(255) NOT NULL,

    -- Paramètres du scénario (identiques à CampaignScenario dans l'API)
    industry VARCHAR(100) NOT NULL,
    company_size VARCHAR(50) NOT NULL,
    city VARCHAR(100) NOT NULL,
    campaign_objective VARCHAR(100) NOT NULL,
    campaign_type VARCHAR(100) NOT NULL,
    channel VARCHAR(100) NOT NULL,
    platform VARCHAR(100) NOT NULL,
    placement VARCHAR(100) NOT NULL,
    target_age VARCHAR(50) NOT NULL,
    target_gender VARCHAR(50) NOT NULL,
    customer_segment VARCHAR(100) NOT NULL,
    creative_format VARCHAR(100) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    duration_days INTEGER NOT NULL,
    budget_xaf NUMERIC(14, 2) NOT NULL,

    -- Instantané de la simulation au moment du lancement (voir docstring)
    predicted_reach NUMERIC(14, 3),
    predicted_engagement_rate_percent NUMERIC(8, 3),
    predicted_ctr_percent NUMERIC(8, 3),
    predicted_roas NUMERIC(10, 3),

    status VARCHAR(30) NOT NULL DEFAULT 'launched',
    launched_at TIMESTAMP NOT NULL DEFAULT now(),
    end_date TIMESTAMP NOT NULL
);
"""


def create_table():
    """Crée la table launched_campaigns si elle n'existe pas déjà.
    Sans danger de la relancer plusieurs fois (IF NOT EXISTS)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))


def generate_campaign_id() -> str:
    """Génère un identifiant court et unique pour la campagne,
    ex. KYZ-CMP-A1B2C3D4."""
    return f"KYZ-CMP-{uuid.uuid4().hex[:8].upper()}"


def launch_campaign(scenario: dict, campaign_name: str, predictions: dict, tenant_id: str = None) -> dict:
    """
    Enregistre une campagne lancée par l'utilisateur, avec l'instantané de
    la simulation au moment du lancement.

    Retourne les informations de la campagne créée (campaign_id, dates...).
    """
    engine = get_engine()
    campaign_id = generate_campaign_id()
    launched_at = datetime.utcnow()
    end_date = launched_at + timedelta(days=int(scenario["duration_days"]))

    insert_sql = text(f"""
        INSERT INTO {TABLE_NAME} (
            campaign_id, tenant_id, campaign_name,
            industry, company_size, city, campaign_objective, campaign_type,
            channel, platform, placement, target_age, target_gender,
            customer_segment, creative_format, content_type,
            duration_days, budget_xaf,
            predicted_reach, predicted_engagement_rate_percent,
            predicted_ctr_percent, predicted_roas,
            status, launched_at, end_date
        ) VALUES (
            :campaign_id, :tenant_id, :campaign_name,
            :industry, :company_size, :city, :campaign_objective, :campaign_type,
            :channel, :platform, :placement, :target_age, :target_gender,
            :customer_segment, :creative_format, :content_type,
            :duration_days, :budget_xaf,
            :predicted_reach, :predicted_engagement_rate_percent,
            :predicted_ctr_percent, :predicted_roas,
            'launched', :launched_at, :end_date
        )
    """)

    params = {
        "campaign_id": campaign_id,
        "tenant_id": tenant_id,
        "campaign_name": campaign_name,
        **scenario,
        "predicted_reach": predictions.get("reach"),
        "predicted_engagement_rate_percent": predictions.get("engagement_rate_percent"),
        "predicted_ctr_percent": predictions.get("ctr_percent"),
        "predicted_roas": predictions.get("roas"),
        "launched_at": launched_at,
        "end_date": end_date,
    }

    with engine.begin() as conn:
        conn.execute(insert_sql, params)

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "status": "launched",
        "launched_at": launched_at.isoformat(),
        "end_date": end_date.isoformat(),
    }
