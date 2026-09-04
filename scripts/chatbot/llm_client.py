"""
Petit utilitaire partage pour appeler le modele local via Ollama.
Utilise par les scripts 04 (text-to-SQL), 05 (RAG) et 06 (chatbot).
"""

import os
import requests

# En local (chatbot lancé directement avec Python), OLLAMA_URL garde sa
# valeur par défaut ci-dessous. En conteneur Docker, cette valeur est
# surchargée via la variable d'environnement OLLAMA_URL (voir docker-compose.yml
# du module de simulation), car "localhost" à l'intérieur d'un conteneur
# désigne le conteneur lui-même, pas la machine hôte où tourne Ollama.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL_NAME = "llama3.2"   # change ici si tu utilises un autre modele Ollama

# Options qui limitent la charge de calcul, pour accelerer les reponses
# sur une machine sans GPU dedie :
#   - num_ctx : taille de la fenetre de contexte prise en compte (plus
#     petit = plus rapide, mais moins de contexte pris en compte)
#   - num_predict : nombre maximum de tokens generes en reponse
#   - keep_alive : garde le modele charge en memoire entre deux appels,
#     pour eviter de le recharger a chaque question (gros gain de temps)
DEFAULT_OPTIONS = {
    "num_ctx": 2048,
    "num_predict": 400,
}
KEEP_ALIVE = "30m"


def ask_llm(system_prompt: str, user_message: str, temperature: float = 0.3) -> str:
    """
    Envoie un system prompt + un message utilisateur au modele local
    via l'API Ollama, et renvoie le texte de la reponse.
    """
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {**DEFAULT_OPTIONS, "temperature": temperature},
    }

    # Timeout genereux : le tout premier appel doit charger le modele en
    # memoire (peut prendre 1-2 minutes sur CPU), les appels suivants sont
    # plus rapides grace a keep_alive.
    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"]
