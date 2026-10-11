"""
Recommandations, par le LLM, pour une campagne en cours ou a venir, a
partir de tout ce que Liyanza-backend sait d'elle : parametres (objectif,
audience, budget, dates), simulation, resultats reels Facebook Ads, alertes
ouvertes, diffusions radio, suivi terrain des supports publicitaires.

La sortie est un JSON impose a Gemini (RECOMMENDATIONS_SCHEMA), puis
reverifie ici : le backend enregistre chaque recommandation telle quelle.

Importe par chatbot_api.py (POST /campaign/recommendations).
"""

import json
from pathlib import Path

from llm_client import ask_llm_json

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = SCRIPT_DIR / "system_prompt_recommendations.md"

PRIORITIES = ("high", "medium", "low")
CATEGORIES = ("budget", "audience", "creative", "channel", "timing", "field", "radio", "measurement")

RECOMMENDATIONS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "recommendations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "detail": {"type": "STRING"},
                    "priority": {"type": "STRING", "enum": list(PRIORITIES)},
                    "category": {"type": "STRING", "enum": list(CATEGORIES)},
                },
                "required": ["title", "detail", "priority", "category"],
            },
        },
    },
    "required": ["recommendations"],
}

MAX_ITEMS = 5


def load_recommendations_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"{SYSTEM_PROMPT_PATH} introuvable.")
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def recommend_for_campaign(context: dict, system_prompt: str) -> dict:
    """
    `context` : donnees de la campagne envoyees par le backend (deja
    validees par le modele Pydantic de l'API). Renvoie
    {"recommendations": [{title, detail, priority, category}]}, triees de la
    plus a la moins prioritaire, 5 au plus.
    """
    user_message = (
        "Voici la campagne a conseiller (donnees fournies par la plateforme, "
        "a ne pas completer par des chiffres inventes) :\n\n"
        + json.dumps(context, ensure_ascii=False, indent=1)
    )
    raw = ask_llm_json(system_prompt, user_message, RECOMMENDATIONS_SCHEMA, temperature=0.4)

    items = []
    for r in raw.get("recommendations") or []:
        if not isinstance(r, dict):
            continue
        title = str(r.get("title", "")).strip()
        detail = str(r.get("detail", "")).strip()
        if not title or not detail:
            continue
        priority = str(r.get("priority", "")).strip().lower()
        category = str(r.get("category", "")).strip().lower()
        items.append({
            "title": title,
            "detail": detail,
            "priority": priority if priority in PRIORITIES else "medium",
            "category": category if category in CATEGORIES else "measurement",
        })
    if not items:
        raise RuntimeError("Gemini n'a renvoye aucune recommandation exploitable")

    items.sort(key=lambda r: PRIORITIES.index(r["priority"]))
    return {"recommendations": items[:MAX_ITEMS]}
