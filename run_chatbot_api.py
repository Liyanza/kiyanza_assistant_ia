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

if __name__ == "__main__":
    uvicorn.run("chatbot_api:app", host="0.0.0.0", port=8000, reload=RELOAD_ENABLED)
