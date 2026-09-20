"""
Lance l'API de simulation de campagne (Kiyanza).

IMPORTANT : à exécuter depuis la racine du projet.

Usage :
    python run_api.py

L'API sera accessible sur http://localhost:8001
Documentation interactive (Swagger) : http://localhost:8001/docs
"""

import os
import sys
from pathlib import Path

SIMULATION_DIR = Path(__file__).resolve().parent / "scripts" / "simulation"
sys.path.insert(0, str(SIMULATION_DIR))

import uvicorn  # noqa: E402

RELOAD_ENABLED = os.environ.get("API_RELOAD", "true").lower() == "true"
# Render (et d'autres hébergeurs cloud) imposent leur propre port via la
# variable d'environnement PORT — on l'utilise si présente, sinon on garde
# 8001 par défaut pour le développement local.
PORT = int(os.environ.get("PORT", 8001))

if __name__ == "__main__":
    uvicorn.run("simulation_api:app", host="0.0.0.0", port=PORT, reload=RELOAD_ENABLED)
