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

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY run_api.py .
COPY scripts/simulation/ ./scripts/simulation/
COPY scripts/chatbot/llm_client.py ./scripts/chatbot/llm_client.py

COPY data/simulation/ ./data/simulation/
COPY models/simulation/ ./models/simulation/

EXPOSE 8001

ENV API_RELOAD=false

CMD ["python", "run_api.py"]
