"""
Analyse, par le LLM, de la sante d'une Page Facebook calculee par
Liyanza-backend (statistiques des 28 derniers jours, meilleures
publications, meilleurs creneaux de publication). Le backend garde les
chiffres ; ce module les explique et propose des actions.

La sortie est un JSON impose a Gemini (PAGE_HEALTH_ANALYSIS_SCHEMA), puis
reverifie ici avant d'etre renvoye au backend.

Importe par chatbot_api.py (POST /page-health/analyze).
"""

import json
from pathlib import Path

from llm_client import ask_llm_json

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = SCRIPT_DIR / "system_prompt_page_health.md"

PAGE_HEALTH_ANALYSIS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "watchouts": {"type": "ARRAY", "items": {"type": "STRING"}},
        "actions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"title": {"type": "STRING"}, "detail": {"type": "STRING"}},
                "required": ["title", "detail"],
            },
        },
    },
    "required": ["summary", "strengths", "watchouts", "actions"],
}

MAX_ITEMS = 3


def load_page_health_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"{SYSTEM_PROMPT_PATH} introuvable.")
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _texts(value) -> list[str]:
    return [str(v).strip() for v in (value or []) if str(v).strip()][:MAX_ITEMS]


def analyze_page_health(health: dict, system_prompt: str) -> dict:
    """
    `health` : indicateurs calcules par le backend (deja valides par le
    modele Pydantic de l'API). Renvoie un dict conforme a
    PAGE_HEALTH_ANALYSIS_SCHEMA, nettoye (listes bornees, textes non vides).
    """
    user_message = (
        "Voici les statistiques de la Page Facebook a analyser (donnees fournies "
        "par la plateforme, a ne pas completer par des chiffres inventes) :\n\n"
        + json.dumps(health, ensure_ascii=False, indent=1)
    )
    raw = ask_llm_json(system_prompt, user_message, PAGE_HEALTH_ANALYSIS_SCHEMA, temperature=0.4)

    summary = str(raw.get("summary", "")).strip()
    if not summary:
        raise RuntimeError("Analyse Gemini sans resume")

    actions = [
        {"title": str(a.get("title", "")).strip(), "detail": str(a.get("detail", "")).strip()}
        for a in (raw.get("actions") or [])
        if isinstance(a, dict) and str(a.get("title", "")).strip()
    ][:MAX_ITEMS]

    return {
        "summary": summary,
        "strengths": _texts(raw.get("strengths")),
        "watchouts": _texts(raw.get("watchouts")),
        "actions": actions,
    }
