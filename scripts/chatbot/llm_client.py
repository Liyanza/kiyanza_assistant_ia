"""
Petit utilitaire partage pour appeler le modele via l'API Gemini de Google.

Remplace l'ancienne version basee sur Ollama local : meme interface
publique (ask_llm), donc aucun autre fichier du projet n'a besoin d'etre
modifie (chatbot.py, simulation_text.py, communication_plan.py continuent
d'appeler ask_llm(system_prompt, user_message, temperature) exactement pareil).

Pourquoi ce changement : Ollama necessite une machine avec suffisamment de
RAM tournant en permanence (contrainte forte pour l'hebergement en ligne).
L'API Gemini est gratuite jusqu'a 1000 requetes/jour, et tres bon marche
au-dela (~0,10$ pour 1 million de tokens sur le modele le moins cher) —
voir https://ai.google.dev/gemini-api/docs/pricing pour les tarifs a jour.

Pre-requis : une cle API gratuite sur https://aistudio.google.com/apikey,
a placer dans le fichier .env sous le nom GEMINI_API_KEY.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Modele par defaut : rapide et bon marche (eligible au niveau gratuit).
# Modifiable via la variable d'environnement GEMINI_MODEL si besoin, sans
# toucher au code. Verifie le nom exact des modeles disponibles sur
# https://ai.google.dev/gemini-api/docs/models si celui-ci venait a changer.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def ask_llm(system_prompt: str, user_message: str, temperature: float = 0.3) -> str:
    """
    Envoie un system prompt + un message utilisateur a l'API Gemini, et
    renvoie le texte de la reponse. Meme signature que l'ancienne version
    Ollama : aucun appelant n'a besoin de changer.
    """
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY n'est pas definie. Ajoute-la a ton fichier .env "
            "(cle gratuite sur https://aistudio.google.com/apikey)."
        )

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": temperature},
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    response = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Reponse Gemini inattendue (pas de texte trouve) : {data}")
