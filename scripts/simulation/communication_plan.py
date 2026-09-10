"""
Génération du plan marketing et de communication d'une campagne déjà
lancée (Kiyanza - cahier des charges IA, section 4.3 "Génération d'un plan
marketing et de communication").

Contrairement à la simulation (§4.4), qui prédit des chiffres avant même de
savoir si l'utilisateur ira au bout, cette brique s'applique à une campagne
DÉJÀ enregistrée (table launched_campaigns) : elle rédige, via le LLM local
(Ollama, réutilise llm_client.py du chatbot), une proposition de stratégie
et de calendrier de communication cohérente avec le scénario simulé.

Le plan est généré UNE SEULE FOIS par campagne puis mis en cache en base
(voir campaign_launch.py : save_communication_plan / colonne
communication_plan_text) — un appel LLM coûte plusieurs secondes, pas de
raison de le refaire à chaque consultation.

Convention du projet : importé par l'API, ne doit jamais être exécuté
directement.
"""

import sys
from pathlib import Path

# scripts/simulation/ et scripts/chatbot/ sont deux dossiers frères : on
# ajoute explicitement scripts/chatbot/ au chemin d'import pour réutiliser
# llm_client.py sans le dupliquer (même technique que simulation_text.py).
CHATBOT_DIR = Path(__file__).resolve().parent.parent / "chatbot"
if str(CHATBOT_DIR) not in sys.path:
    sys.path.insert(0, str(CHATBOT_DIR))

from llm_client import ask_llm  # noqa: E402
from campaign_launch import get_campaign_by_id, save_communication_plan  # noqa: E402

TEMPLATE_PATH = Path(__file__).resolve().parent / "communication_plan_template.md"


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"{TEMPLATE_PATH} introuvable.")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_system_prompt() -> str:
    template = load_template()
    return (
        "Tu es l'assistant marketing IA de Kiyanza. Ton rôle ici est de "
        "rédiger le plan marketing et de communication d'une campagne que "
        "l'entreprise a déjà décidé de lancer.\n\n"
        "Voici la méthodologie exacte à suivre (structure, règles de "
        "gestion, ton) :\n\n" + template
    )


def build_user_message(campaign: dict) -> str:
    """Construit le message décrivant la campagne lancée, envoyé au LLM
    pour qu'il rédige le plan."""

    lines = ["CAMPAGNE LANCÉE :"]
    lines.append(f"- Nom de la campagne : {campaign['campaign_name']}")
    lines.append(f"- Secteur : {campaign['industry']}")
    lines.append(f"- Taille de l'entreprise : {campaign['company_size']}")
    lines.append(f"- Ville : {campaign['city']}")
    lines.append(f"- Objectif : {campaign['campaign_objective']}")
    lines.append(f"- Canal principal : {campaign['channel']} (plateforme : {campaign['platform']})")
    lines.append(f"- Format créatif : {campaign['creative_format']} / {campaign['content_type']}")
    lines.append(
        f"- Cible : {campaign['target_age']}, {campaign['target_gender']}, "
        f"segment {campaign['customer_segment']}"
    )
    lines.append(f"- Durée : {campaign['duration_days']} jours")
    lines.append(f"- Budget total : {float(campaign['budget_xaf']):,.0f} FCFA".replace(",", " "))

    lines.append("\nRÉSULTATS ESTIMÉS PAR LA SIMULATION (à prendre en compte, ne pas re-décrire en détail) :")
    lines.append(f"- Portée estimée : {float(campaign['predicted_reach']):,.0f} personnes".replace(",", " "))
    lines.append(f"- Engagement estimé : {float(campaign['predicted_engagement_rate_percent']):.2f}%")
    lines.append(f"- ROAS estimé : x{float(campaign['predicted_roas']):.1f}")

    lines.append(
        "\nRédige maintenant le plan marketing et de communication pour "
        "cette campagne, en respectant strictement la méthodologie fournie."
    )

    return "\n".join(lines)


def generate_communication_plan(campaign_id: str, force_regenerate: bool = False) -> dict:
    """
    Récupère (ou génère puis met en cache) le plan marketing et de
    communication d'une campagne déjà lancée.

    Retourne None si la campagne n'existe pas (à l'appelant de renvoyer une
    erreur 404 côté API).
    """
    campaign = get_campaign_by_id(campaign_id)
    if campaign is None:
        return None

    if campaign.get("communication_plan_text") and not force_regenerate:
        return {
            "campaign_id": campaign_id,
            "plan_text": campaign["communication_plan_text"],
            "generated_at": campaign["communication_plan_generated_at"].isoformat(),
            "cached": True,
        }

    system_prompt = build_system_prompt()
    user_message = build_user_message(campaign)
    plan_text = ask_llm(system_prompt, user_message, temperature=0.4)

    save_communication_plan(campaign_id, plan_text)
    updated_campaign = get_campaign_by_id(campaign_id)

    return {
        "campaign_id": campaign_id,
        "plan_text": plan_text,
        "generated_at": updated_campaign["communication_plan_generated_at"].isoformat(),
        "cached": False,
    }
