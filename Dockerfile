# Image de l'API de simulation de campagne Kiyanza (fonctionnalité 4.4
# "Simuler avant de dépenser").
#
# Ne contient QUE ce dont l'API a besoin pour répondre aux requêtes :
# le code de scripts/simulation/, le client Ollama partagé avec le chatbot
# (llm_client.py), et les modèles déjà entraînés (models/simulation/) +
# les données de référence pour l'explicabilité (data/simulation/).
#
# Ollama n'est PAS inclus dans cette image : il continue de tourner sur la
# machine hôte, et ce conteneur s'y connecte via OLLAMA_URL (voir
# docker-compose.yml).

FROM python:3.11-slim

WORKDIR /app

# build-essential : nécessaire si pip doit compiler une dépendance depuis
# les sources (pas de "wheel" précompilée disponible pour cette plateforme).
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# --- Code de l'application -------------------------------------------------
COPY run_api.py .
COPY scripts/simulation/ ./scripts/simulation/
COPY scripts/chatbot/llm_client.py ./scripts/chatbot/llm_client.py

# --- Artefacts déjà entraînés (générés par les étapes 1 et 2) --------------
# Si ces dossiers n'existent pas encore chez toi au moment du build, lance
# d'abord 07_prepare_simulation_data.py et 08_train_simulation_models.py.
COPY data/simulation/ ./data/simulation/
COPY models/simulation/ ./models/simulation/

EXPOSE 8001

# Désactive le rechargement automatique (non pertinent pour une image figée)
ENV API_RELOAD=false

CMD ["python", "run_api.py"]
