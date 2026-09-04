"""
Lance l'API de simulation de campagne (Kiyanza).

IMPORTANT : à exécuter depuis la racine du projet (là où se trouve ce
fichier), pour que les chemins relatifs vers data/simulation/ et
models/simulation/ fonctionnent correctement.

Usage :
    python run_api.py

L'API sera accessible sur http://localhost:8001
Documentation interactive (Swagger) : http://localhost:8001/docs
"""

import os
import sys
from pathlib import Path

# scripts/simulation/ n'est pas automatiquement sur le chemin d'import de
# Python quand on lance ce fichier depuis la racine (contrairement à quand
# on exécute un script numéroté directement, qui bénéficie de l'ajout
# automatique de son propre dossier). On l'ajoute donc explicitement, une
# fois, ici.
SIMULATION_DIR = Path(__file__).resolve().parent / "scripts" / "simulation"
sys.path.insert(0, str(SIMULATION_DIR))

import uvicorn  # noqa: E402  (import après modification de sys.path, volontaire)

# Rechargement automatique à chaque modification du code : pratique en
# développement local, à désactiver en conteneur Docker (API_RELOAD=false
# dans docker-compose.yml) — le rechargement suppose un système de fichiers
# qui change en direct, ce qui n'a pas de sens pour une image figée.
RELOAD_ENABLED = os.environ.get("API_RELOAD", "true").lower() == "true"

if __name__ == "__main__":
    uvicorn.run("simulation_api:app", host="0.0.0.0", port=8001, reload=RELOAD_ENABLED)
