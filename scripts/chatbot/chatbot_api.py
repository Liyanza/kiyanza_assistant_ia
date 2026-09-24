"""
API FastAPI du chatbot Kiyanza, mode "Poser une question" (cahier des
charges IA, section 4.1.A).

Un seul endpoint métier : POST /ask, qui reprend exactement la même logique
que 06_chatbot.py (RAG + Text-to-SQL + appel LLM Gemini), réutilisée sans
duplication via chatbot.py.

Ce service n'est appelé QUE par Liyanza-backend (NestJS), jamais directement
par un navigateur ou l'app mobile : c'est le backend qui authentifie
l'utilisateur, vérifie son entreprise, puis relaie la question ici avec le
secret partagé X-Internal-Token. D'où l'absence volontaire de CORS.

Contrat (voir Liyanza-backend, src/modules/assistant-ia/clients/ia-engine.interface.ts) :

    POST /ask
    X-Internal-Token: <INTERNAL_TOKEN>
    {
      "conversationId": "...",            (optionnel)
      "userMessage": "...",
      "context": {                         (optionnel)
        "topic": "...",
        "companyProfile": {"name", "businessSector", "address"},
        "recentMessages": [{"sender": "USER"|"AI", "content": "..."}]
      }
    }
    -> {"answer": "..."}

Prérequis : GEMINI_API_KEY et INTERNAL_TOKEN définis, base vectorielle
Chroma construite (étape 3 du pipeline chatbot). PostgreSQL (Text-to-SQL)
est facultatif : s'il est injoignable, le chatbot répond sans les données
chiffrées.

IMPORTANT : à lancer depuis la racine du projet.
"""

import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from chatbot import load_system_prompt, answer_question
from rag_retrieve import warm_up as warm_up_rag

logger = logging.getLogger("kiyanza.chatbot_api")

# Lu une seule fois au démarrage. Le service refuse de démarrer sans lui :
# exposé sur Internet sans secret, n'importe qui pourrait consommer le quota
# Gemini (§6 du canevas d'intégration backend).
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")
MIN_TOKEN_LENGTH = 32

_system_prompt = None


class CompanyProfile(BaseModel):
    name: str | None = None
    businessSector: str | None = None
    address: str | None = None


class RecentMessage(BaseModel):
    sender: Literal["USER", "AI"]
    content: str


class AskContext(BaseModel):
    topic: str | None = None
    companyProfile: CompanyProfile | None = None
    recentMessages: list[RecentMessage] = Field(default_factory=list, max_length=20)


class AskRequest(BaseModel):
    conversationId: str | None = None
    userMessage: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        examples=["Comment toucher plus de clients à Douala avec un petit budget ?"],
    )
    context: AskContext | None = None


class AskResponse(BaseModel):
    answer: str


def verify_internal_token(x_internal_token: str = Header(default="")) -> None:
    # Comparaison à temps constant sur des empreintes de taille fixe : une
    # simple égalité `==` fuiterait la longueur du préfixe correct.
    expected = hashlib.sha256(INTERNAL_TOKEN.encode()).digest()
    received = hashlib.sha256(x_internal_token.encode()).digest()
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(INTERNAL_TOKEN) < MIN_TOKEN_LENGTH:
        raise RuntimeError(
            f"INTERNAL_TOKEN doit être défini et faire au moins {MIN_TOKEN_LENGTH} "
            "caractères (ex: openssl rand -hex 32)."
        )

    global _system_prompt
    _system_prompt = load_system_prompt()

    # Charge le modèle d'embeddings et la base Chroma dès le démarrage :
    # sinon la première question paie 10 à 20 s de chargement, et une base
    # Chroma absente ne se découvrirait qu'au premier appel.
    warm_up_rag()
    yield


app = FastAPI(
    title="Kiyanza - API du chatbot",
    description="Fonctionnalité 4.1.A du cahier des charges IA : "
                 "'Assistant IA marketing — mode Poser une question'.",
    version="1.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(verify_internal_token)])
def ask(request: AskRequest):
    """Pose une question au chatbot marketing de Kiyanza."""
    context = request.context or AskContext()
    try:
        answer = answer_question(
            request.userMessage,
            _system_prompt,
            topic=context.topic,
            company_profile=context.companyProfile.model_dump(exclude_none=True)
            if context.companyProfile
            else None,
            recent_messages=[m.model_dump() for m in context.recentMessages],
        )
    except Exception:
        # Le détail (clé API invalide, quota Gemini, Chroma corrompue...)
        # reste dans les logs du serveur : le renvoyer au client exposerait
        # des informations internes (§6.3 : informer sans divulguer).
        logger.exception("Échec du traitement de /ask (conversation %s)", request.conversationId)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Le chatbot est temporairement indisponible.",
        )
    return {"answer": answer}
