"""
Table et fonctions de gestion des diffusions radio planifiées (Kiyanza -
cahier des charges IA, section 4.7 "Monitoring intelligent des diffusions
radio").

Une ligne = UNE diffusion prévue (ex. "le spot X doit passer sur Balafon à
8h05 le 15 mars"). Une même campagne radio peut avoir plusieurs lignes
(plusieurs horaires de diffusion prévus).

Table séparée de launched_campaigns (campagnes digitales) : le monitoring
radio a son propre cycle de vie (planification -> capture -> détection),
indépendant du reste de la simulation.
"""

import os
import uuid
from datetime import datetime, timedelta

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

TABLE_NAME = "radio_monitoring_schedule"

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
    schedule_id VARCHAR(32) UNIQUE NOT NULL,
    campaign_id VARCHAR(32),                   -- optionnel, lien vers launched_campaigns si pertinent

    station_name VARCHAR(255) NOT NULL,
    stream_url TEXT NOT NULL,
    reference_spot_path TEXT NOT NULL,          -- empreinte audio du spot fournie par l'utilisateur

    planned_datetime TIMESTAMP NOT NULL,        -- heure à laquelle le spot doit être diffusé
    capture_lead_minutes INTEGER NOT NULL DEFAULT 5,   -- marge avant l'heure prévue pour commencer à écouter
    capture_duration_seconds INTEGER NOT NULL DEFAULT 900,  -- durée totale d'écoute (par défaut 15 min)

    status VARCHAR(30) NOT NULL DEFAULT 'pending',  -- pending -> scheduled -> processing -> completed/failed

    detected BOOLEAN,
    detected_at TIMESTAMP,
    deviation_minutes NUMERIC(8, 2),
    best_score NUMERIC(6, 4),
    error_message TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT now(),
    processed_at TIMESTAMP
);
"""


def create_table():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))


def generate_schedule_id() -> str:
    return f"KYZ-RADIO-{uuid.uuid4().hex[:8].upper()}"


def create_monitoring_entry(
    station_name: str,
    stream_url: str,
    reference_spot_path: str,
    planned_datetime: datetime,
    campaign_id: str = None,
    capture_lead_minutes: int = 5,
    capture_duration_seconds: int = 900,
) -> str:
    """Enregistre une nouvelle diffusion prévue à surveiller. Retourne le
    schedule_id généré."""
    engine = get_engine()
    schedule_id = generate_schedule_id()

    insert_sql = text(f"""
        INSERT INTO {TABLE_NAME} (
            schedule_id, campaign_id, station_name, stream_url,
            reference_spot_path, planned_datetime,
            capture_lead_minutes, capture_duration_seconds
        ) VALUES (
            :schedule_id, :campaign_id, :station_name, :stream_url,
            :reference_spot_path, :planned_datetime,
            :capture_lead_minutes, :capture_duration_seconds
        )
    """)
    with engine.begin() as conn:
        conn.execute(insert_sql, {
            "schedule_id": schedule_id,
            "campaign_id": campaign_id,
            "station_name": station_name,
            "stream_url": stream_url,
            "reference_spot_path": reference_spot_path,
            "planned_datetime": planned_datetime,
            "capture_lead_minutes": capture_lead_minutes,
            "capture_duration_seconds": capture_duration_seconds,
        })

    return schedule_id


def get_entry(schedule_id: str) -> dict:
    engine = get_engine()
    select_sql = text(f"SELECT * FROM {TABLE_NAME} WHERE schedule_id = :schedule_id")
    with engine.connect() as conn:
        row = conn.execute(select_sql, {"schedule_id": schedule_id}).mappings().first()
    return dict(row) if row else None


def get_entries_ready_to_schedule(lookahead_minutes: int = 2) -> list:
    """
    Retourne les diffusions encore 'pending' dont le moment de démarrage de
    capture (planned_datetime - capture_lead_minutes) tombe dans les
    lookahead_minutes à venir — c'est-à-dire celles qu'il faut programmer
    MAINTENANT dans Celery avant le prochain passage du planificateur.
    """
    engine = get_engine()
    select_sql = text(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE status = 'pending'
        AND (planned_datetime - (capture_lead_minutes || ' minutes')::interval) <= now() + (:lookahead || ' minutes')::interval
    """)
    with engine.connect() as conn:
        rows = conn.execute(select_sql, {"lookahead": lookahead_minutes}).mappings().all()
    return [dict(r) for r in rows]


def mark_status(schedule_id: str, status: str):
    engine = get_engine()
    update_sql = text(f"UPDATE {TABLE_NAME} SET status = :status WHERE schedule_id = :schedule_id")
    with engine.begin() as conn:
        conn.execute(update_sql, {"schedule_id": schedule_id, "status": status})


def save_result(
    schedule_id: str,
    detected: bool,
    detected_at: datetime = None,
    deviation_minutes: float = None,
    best_score: float = None,
    error_message: str = None,
):
    """Enregistre le résultat final de la détection pour une diffusion
    planifiée, et marque son statut en conséquence."""
    engine = get_engine()
    status = "failed" if error_message else "completed"

    update_sql = text(f"""
        UPDATE {TABLE_NAME}
        SET status = :status, detected = :detected, detected_at = :detected_at,
            deviation_minutes = :deviation_minutes, best_score = :best_score,
            error_message = :error_message, processed_at = :processed_at
        WHERE schedule_id = :schedule_id
    """)
    with engine.begin() as conn:
        conn.execute(update_sql, {
            "schedule_id": schedule_id,
            "status": status,
            "detected": detected,
            "detected_at": detected_at,
            "deviation_minutes": deviation_minutes,
            "best_score": best_score,
            "error_message": error_message,
            "processed_at": datetime.utcnow(),
        })


def get_entries_for_report(campaign_id: str = None, station_name: str = None) -> list:
    """
    Récupère les diffusions déjà traitées (completed ou failed — on exclut
    pending/scheduled/processing, pas encore de résultat à rapporter),
    filtrées par campagne et/ou station, triées par heure prévue.
    """
    engine = get_engine()
    conditions = ["status IN ('completed', 'failed')"]
    params = {}

    if campaign_id:
        conditions.append("campaign_id = :campaign_id")
        params["campaign_id"] = campaign_id
    if station_name:
        conditions.append("station_name = :station_name")
        params["station_name"] = station_name

    where_clause = " AND ".join(conditions)
    select_sql = text(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE {where_clause}
        ORDER BY planned_datetime ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(select_sql, params).mappings().all()
    return [dict(r) for r in rows]


def get_entries(campaign_id: str = None, station_name: str = None) -> list:
    """
    Récupère TOUTES les diffusions (peu importe leur statut : pending,
    scheduled, processing, completed, failed), filtrées par campagne et/ou
    station, triées par heure prévue. Utile pour le suivi en temps réel
    depuis l'API (contrairement à get_entries_for_report, qui ne renvoie
    que celles déjà traitées, pour la génération de rapport).
    """
    engine = get_engine()
    conditions = ["1=1"]
    params = {}

    if campaign_id:
        conditions.append("campaign_id = :campaign_id")
        params["campaign_id"] = campaign_id
    if station_name:
        conditions.append("station_name = :station_name")
        params["station_name"] = station_name

    where_clause = " AND ".join(conditions)
    select_sql = text(f"""
        SELECT * FROM {TABLE_NAME}
        WHERE {where_clause}
        ORDER BY planned_datetime ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(select_sql, params).mappings().all()
    return [dict(r) for r in rows]
