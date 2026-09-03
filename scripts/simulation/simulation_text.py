"""
Génération du texte final de simulation de campagne, en français clair,
à partir des prédictions chiffrées + facteurs explicatifs (étape 3).

Kiyanza - fonctionnalité 4.4 "Simuler avant de dépenser".

Ce module :
1. Réutilise predict_and_explain() (étape 3) pour obtenir les 4 prédictions
   et leurs facteurs explicatifs
2. Construit un message structuré résumant ces informations
3. Appelle le LLM local (Ollama, via llm_client.py du chatbot) pour rédiger
   une estimation compréhensible en français, avec ses points forts, ses
   limites, et des suggestions d'ajustement

Règles imposées par le cahier des charges (§4.4, §6.1) et codées dans le
system prompt ci-dessous :
    - Toujours présenter le résultat comme une ESTIMATION, jamais une garantie
    - Français clair, sans jargon technique inutile
    - Expliquer pourquoi (transparence minimale)
    - Rester réaliste pour une petite structure (budgets limités, §6.5)

Convention du projet : importé par 10_generate_simulation_text.py, ne doit
jamais être exécuté directement.
"""

import sys
from pathlib import Path

# scripts/simulation/ et scripts/chatbot/ sont deux dossiers frères : Python
# n'ajoute automatiquement au chemin d'import que le dossier du script en
# cours d'exécution, pas ses voisins. On ajoute donc explicitement
# scripts/chatbot/ pour pouvoir réutiliser llm_client.py sans le dupliquer.
CHATBOT_DIR = Path(__file__).resolve().parent.parent / "chatbot"
if str(CHATBOT_DIR) not in sys.path:
    sys.path.insert(0, str(CHATBOT_DIR))

from llm_client import ask_llm  # noqa: E402  (import après modification de sys.path, volontaire)
from simulation_explain import predict_and_explain  # noqa: E402


SYSTEM_PROMPT = """Tu es l'assistant marketing IA de Kiyanza, une plateforme qui aide les \
petites et moyennes entreprises des marchés émergents (Cameroun notamment) à \
préparer leurs campagnes marketing.

Ton rôle ici : transformer une prédiction chiffrée en une estimation \
compréhensible pour un entrepreneur qui n'a pas d'expertise marketing ou \
technique, AVANT qu'il ne lance sa campagne.

RÈGLES STRICTES À RESPECTER :
1. Tu dois TOUJOURS rappeler clairement qu'il s'agit d'une ESTIMATION, \
jamais d'une garantie de résultat. Ne formule jamais une prédiction comme \
un fait certain.
2. Utilise un français clair, simple, sans jargon technique. Si tu emploies \
un terme comme "CTR" ou "ROAS", explique-le brièvement entre parenthèses \
la première fois.
3. Base-toi UNIQUEMENT sur les chiffres et facteurs qui te sont fournis. \
N'invente jamais de statistique, de canal, ou de fonctionnalité qui ne \
serait pas mentionnée dans les données fournies.
4. Structure toujours ta réponse en 4 parties, avec des titres courts :
   - **Ce à quoi t'attendre** : les performances estimées (portée, \
engagement, taux de clic, retour sur investissement), en une ou deux phrases.
   - **Pourquoi ces chiffres** : explique les 1 à 2 facteurs les plus \
importants (positifs et/ou négatifs) fournis dans les données, dans un \
langage simple (pas de nom de variable technique).
   - **Points de vigilance** : les limites ou incertitudes de cette \
estimation.
   - **Pistes d'ajustement** : 1 à 2 suggestions concrètes et réalistes, \
adaptées à une petite structure avec un budget limité (pas de recommandation \
nécessitant des moyens hors de portée d'une PME).
5. Reste bref : 150 à 220 mots maximum au total.
6. Si des avertissements te signalent une valeur inconnue ou non fiable, \
mentionne-le brièvement sans dramatiser, en expliquant que cela réduit \
légèrement la précision de l'estimation sur ce point.
"""


def format_metric_label(metric: str) -> str:
    labels = {
        "reach": "la portée (nombre de personnes touchées)",
        "engagement_rate_percent": "le taux d'engagement",
        "ctr_percent": "le taux de clic (CTR)",
        "roas": "le retour sur investissement publicitaire (ROAS)",
    }
    return labels.get(metric, metric)


def format_prediction_value(metric: str, value: float) -> str:
    if metric == "reach":
        return f"{value:,.0f} personnes".replace(",", " ")
    if metric in ("engagement_rate_percent", "ctr_percent"):
        return f"{value:.2f} %"
    if metric == "roas":
        return f"x{value:.1f} (chaque FCFA dépensé rapporte environ {value:.1f} FCFA)"
    return str(value)


def build_user_message(scenario: dict, result: dict) -> str:
    """Construit le message décrivant le scénario + les résultats chiffrés,
    envoyé au LLM pour qu'il rédige le texte final."""

    lines = ["SCÉNARIO DE CAMPAGNE PROPOSÉ :"]
    lines.append(f"- Secteur : {scenario.get('industry')}")
    lines.append(f"- Taille de l'entreprise : {scenario.get('company_size')}")
    lines.append(f"- Ville : {scenario.get('city')}")
    lines.append(f"- Objectif de la campagne : {scenario.get('campaign_objective')}")
    lines.append(f"- Canal : {scenario.get('channel')} (plateforme : {scenario.get('platform')})")
    lines.append(f"- Format créatif : {scenario.get('creative_format')} / {scenario.get('content_type')}")
    lines.append(f"- Cible : {scenario.get('target_age')}, {scenario.get('target_gender')}, segment {scenario.get('customer_segment')}")
    lines.append(f"- Durée : {scenario.get('duration_days')} jours")
    lines.append(f"- Budget : {scenario.get('budget_xaf'):,.0f} FCFA".replace(",", " "))

    lines.append("\nPRÉDICTIONS DU MODÈLE :")
    for metric, value in result["predictions"].items():
        lines.append(f"- {format_metric_label(metric)} : {format_prediction_value(metric, value)}")

    lines.append("\nFACTEURS EXPLICATIFS (comparaison aux moyennes historiques du secteur) :")
    for metric, factors in result["explanations"].items():
        if not factors:
            continue
        lines.append(f"Pour {format_metric_label(metric)} :")
        for f in factors:
            signe = "+" if f["lift_pct"] > 0 else ""
            lines.append(
                f"  - {f['feature']} = \"{f['value']}\" : {signe}{f['lift_pct']}% par rapport "
                f"à la moyenne du secteur (basé sur {f['n_historique']} campagnes similaires)"
            )

    if result["warnings"]:
        lines.append("\nAVERTISSEMENTS :")
        for w in result["warnings"]:
            lines.append(f"- {w}")

    lines.append(
        "\nRédige maintenant l'estimation pour l'utilisateur, en respectant "
        "strictement les règles et la structure définies dans tes instructions."
    )

    return "\n".join(lines)


def generate_simulation_text(scenario: dict, temperature: float = 0.3) -> dict:
    """
    Pipeline complet de l'étape 4 : prédiction + explicabilité (étape 3),
    puis rédaction du texte final en français clair par le LLM.

    Retourne un dict avec le texte final ET les données structurées
    sous-jacentes (utile pour un futur affichage enrichi côté frontend,
    en plus du texte).
    """
    result = predict_and_explain(scenario)
    user_message = build_user_message(scenario, result)
    text = ask_llm(SYSTEM_PROMPT, user_message, temperature=temperature)

    return {
        "text": text,
        "predictions": result["predictions"],
        "explanations": result["explanations"],
        "warnings": result["warnings"],
    }
