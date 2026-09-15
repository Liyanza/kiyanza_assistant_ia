"""
Configuration de l'application Celery pour le monitoring radio (Kiyanza).

Redis sert à la fois de broker (file de tâches) et de backend (stockage
des résultats) — déjà prévu dans l'architecture du projet (section
"Stockage" : Redis = cache + broker Celery).
"""

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "kiyanza_radio_monitoring",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["radio_monitoring_tasks"],
)

app.conf.update(
    timezone="UTC",
    task_track_started=True,
    # Le planificateur (check_upcoming_diffusions) tourne toutes les 60
    # secondes : assez fréquent pour ne rater aucune diffusion planifiée à
    # la minute près, sans surcharger la base de données.
    beat_schedule={
        "check-upcoming-radio-diffusions": {
            "task": "radio_monitoring_tasks.check_upcoming_diffusions",
            "schedule": 60.0,
        },
    },
)
