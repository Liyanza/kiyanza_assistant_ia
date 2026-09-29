"""
Analyse, par le LLM, d'une simulation de campagne digitale calculee par
Liyanza-backend (moteur de references de marche). Le backend garde les
chiffres ; ce module les explique : resume, points forts, risques,
recommandations, choix du scenario.

La sortie est un JSON impose a Gemini (SIMULATION_ANALYSIS_SCHEMA), puis
reverifie ici : le backend l'enregistre tel quel et l'interface l'affiche
bloc par bloc.

Importe par chatbot_api.py (POST /simulation/analyze).
"""

import json
from pathlib import Path

from llm_client import ask_llm_json

SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = SCRIPT_DIR / "system_prompt_simulation.md"

# Format OpenAPI simplifie attendu par Gemini (responseSchema).
SIMULATION_ANALYSIS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
        "risks": {"type": "ARRAY", "items": {"type": "STRING"}},
        "recommendations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"title": {"type": "STRING"}, "detail": {"type": "STRING"}},
                "required": ["title", "detail"],
            },
        },
        "scenarioChoice": {"type": "STRING"},
    },
    "required": ["summary", "strengths", "risks", "recommendations", "scenarioChoice"],
}

MAX_ITEMS = 4


def load_simulation_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"{SYSTEM_PROMPT_PATH} introuvable.")
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def _texts(value) -> list[str]:
    return [str(v).strip() for v in (value or []) if str(v).strip()][:MAX_ITEMS]


def analyze_simulation(simulation: dict, system_prompt: str) -> dict:
    """
    `simulation` : parametres et resultats envoyes par le backend (deja
    valides par le modele Pydantic de l'API). Renvoie un dict conforme a
    SIMULATION_ANALYSIS_SCHEMA, nettoye (listes bornees, textes non vides).
    """
    user_message = (
        "Voici la simulation a analyser (donnees fournies par la plateforme, "
        "a ne pas completer par des chiffres inventes) :\n\n"
        + json.dumps(simulation, ensure_ascii=False, indent=1)
    )
    raw = ask_llm_json(system_prompt, user_message, SIMULATION_ANALYSIS_SCHEMA, temperature=0.3)

    summary = str(raw.get("summary", "")).strip()
    if not summary:
        raise RuntimeError("Analyse Gemini sans resume")

    recommendations = [
        {"title": str(r.get("title", "")).strip(), "detail": str(r.get("detail", "")).strip()}
        for r in (raw.get("recommendations") or [])
        if isinstance(r, dict) and str(r.get("title", "")).strip()
    ][:MAX_ITEMS]

    return {
        "summary": summary,
        "strengths": _texts(raw.get("strengths")),
        "risks": _texts(raw.get("risks")),
        "recommendations": recommendations,
        "scenarioChoice": str(raw.get("scenarioChoice", "")).strip(),
    }
