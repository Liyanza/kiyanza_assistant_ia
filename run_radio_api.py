"""
Lance l'API de monitoring radio (Kiyanza).

IMPORTANT : à exécuter depuis la racine du projet.

Usage :
    python run_radio_api.py

L'API sera accessible sur http://localhost:8002
Documentation interactive (Swagger) : http://localhost:8002/docs

Rappel : pour que les diffusions planifiées soient effectivement traitées,
il faut AUSSI lancer, dans des terminaux séparés :
    cd scripts/radio_monitoring
    celery -A celery_app worker --loglevel=info -P solo
    celery -A celery_app beat --loglevel=info
"""

import os
import sys
from pathlib import Path

RADIO_DIR = Path(__file__).resolve().parent / "scripts" / "radio_monitoring"
sys.path.insert(0, str(RADIO_DIR))

import uvicorn  # noqa: E402

RELOAD_ENABLED = os.environ.get("API_RELOAD", "true").lower() == "true"

if __name__ == "__main__":
    uvicorn.run("radio_monitoring_api:app", host="0.0.0.0", port=8002, reload=RELOAD_ENABLED)
