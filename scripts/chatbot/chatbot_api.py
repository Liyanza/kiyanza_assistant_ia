"""
API FastAPI du chatbot Kiyanza, mode "Poser une question" (cahier des
charges IA, section 4.1.A).

Un seul endpoint : POST /ask, qui reprend exactement la même logique que
06_chatbot.py (RAG + Text-to-SQL + appel LLM), réutilisée sans duplication
via chatbot.py.

Prérequis : Ollama lancé, PostgreSQL lancé (pour le Text-to-SQL), et la
base vectorielle Chroma déjà construite (étape 3 du pipeline chatbot).

IMPORTANT : à lancer depuis la racine du projet.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chatbot import load_system_prompt, answer_question

_system_prompt = None


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, examples=["Comment toucher plus de clients à Douala avec un petit budget ?"])


class AskResponse(BaseModel):
    answer: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Charge le system prompt une seule fois au démarrage, plutôt qu'à
    # chaque requête (fichier texte, coût négligeable, mais autant garder
    # la même logique de préchargement que les autres API du projet).
    global _system_prompt
    _system_prompt = load_system_prompt()
    yield


app = FastAPI(
    title="Kiyanza - API du chatbot",
    description="Fonctionnalité 4.1.A du cahier des charges IA : "
                 "'Assistant IA marketing — mode Poser une question'.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    """Pose une question au chatbot marketing de Kiyanza."""
    try:
        answer = answer_question(request.question, _system_prompt)
    except Exception as e:
        # Couvre Ollama indisponible, PostgreSQL injoignable (Text-to-SQL),
        # ou la base Chroma introuvable/corrompue (RAG) — §6.3 : informer
        # plutôt qu'échouer silencieusement.
        raise HTTPException(
            status_code=503,
            detail=f"Le chatbot est temporairement indisponible : {e}",
        )
    return {"answer": answer}
