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

import json
import os
from collections.abc import Iterator

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Modele par defaut : rapide et bon marche (eligible au niveau gratuit).
# Modifiable via la variable d'environnement GEMINI_MODEL si besoin, sans
# toucher au code. Verifie le nom exact des modeles disponibles sur
# https://ai.google.dev/gemini-api/docs/models si celui-ci venait a changer.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GEMINI_STREAM_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:streamGenerateContent?alt=sse"
)


def _build_request(
    system_prompt: str,
    user_message: str,
    temperature: float,
    api_key: str | None,
    max_output_tokens: int | None,
) -> tuple[dict, dict]:
    api_key = api_key or GEMINI_API_KEY
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY n'est pas definie. Ajoute-la a ton fichier .env "
            "(cle gratuite sur https://aistudio.google.com/apikey)."
        )

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": temperature},
    }
    if max_output_tokens:
        payload["generationConfig"]["maxOutputTokens"] = max_output_tokens
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    return payload, headers


def _candidate_text(data: dict) -> str:
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts)


def ask_llm(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    api_key: str | None = None,
    max_output_tokens: int | None = None,
) -> str:
    """
    Envoie un system prompt + un message utilisateur a l'API Gemini, et
    renvoie le texte de la reponse. Meme signature que l'ancienne version
    Ollama : aucun appelant n'a besoin de changer.

    api_key : cle a utiliser a la place de GEMINI_API_KEY (ex: la cle
    dediee au mode public, pour que les abus du site public ne puissent
    pas epuiser le quota des clients connectes).
    max_output_tokens : plafond de longueur de la reponse.
    """
    payload, headers = _build_request(system_prompt, user_message, temperature, api_key, max_output_tokens)

    response = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()

    text = _candidate_text(data)
    if not text:
        raise RuntimeError(f"Reponse Gemini inattendue (pas de texte trouve) : {data}")
    return text


def ask_llm_stream(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    api_key: str | None = None,
    max_output_tokens: int | None = None,
) -> Iterator[str]:
    """
    Meme appel qu'ask_llm, mais renvoie la reponse morceau par morceau, au
    fil de sa generation par Gemini (streamGenerateContent, format SSE).
    L'erreur HTTP eventuelle est levee au premier next(), avant tout texte.
    """
    payload, headers = _build_request(system_prompt, user_message, temperature, api_key, max_output_tokens)

    # timeout=(connexion, lecture entre deux morceaux) : pas de limite sur la
    # duree totale, mais un flux bloque plus de 60 s est abandonne.
    with requests.post(GEMINI_STREAM_URL, json=payload, headers=headers, stream=True, timeout=(10, 60)) as response:
        response.raise_for_status()
        response.encoding = "utf-8"
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            text = _candidate_text(json.loads(line[len("data:"):].strip()))
            if text:
                yield text


def ask_llm_json(
    system_prompt: str,
    user_message: str,
    response_schema: dict,
    temperature: float = 0.3,
    api_key: str | None = None,
) -> dict:
    """
    Meme appel qu'ask_llm, mais Gemini doit repondre un objet JSON conforme a
    `response_schema` (sortie structuree : responseMimeType + responseSchema,
    format OpenAPI simplifie de Gemini). Renvoie l'objet deja decode.
    """
    payload, headers = _build_request(system_prompt, user_message, temperature, api_key, None)
    payload["generationConfig"]["responseMimeType"] = "application/json"
    payload["generationConfig"]["responseSchema"] = response_schema

    response = requests.post(GEMINI_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()

    text = _candidate_text(data)
    if not text:
        raise RuntimeError(f"Reponse Gemini inattendue (pas de texte trouve) : {data}")
    return json.loads(text)
