"""
Lance l'API du chatbot Kiyanza (mode "Poser une question").

IMPORTANT : à exécuter depuis la racine du projet.

Usage :
    python run_chatbot_api.py

L'API sera accessible sur http://localhost:8000
Documentation interactive (Swagger) : http://localhost:8000/docs
"""

import os
import sys
from pathlib import Path

CHATBOT_DIR = Path(__file__).resolve().parent / "scripts" / "chatbot"
sys.path.insert(0, str(CHATBOT_DIR))

import uvicorn  # noqa: E402

RELOAD_ENABLED = os.environ.get("API_RELOAD", "true").lower() == "true"
# Render (et d'autres hébergeurs cloud) imposent leur propre port via la
# variable d'environnement PORT — on l'utilise si présente, sinon on garde
# 8000 par défaut pour le développement local.
PORT = int(os.environ.get("PORT", 8000))

if __name__ == "__main__":
    uvicorn.run("chatbot_api:app", host="0.0.0.0", port=PORT, reload=RELOAD_ENABLED)
