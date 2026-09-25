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
      "mode": "expert" | "public",        (optionnel, "expert" par défaut)
      "conversationId": "...",            (optionnel)
      "userMessage": "...",
      "context": {                         (optionnel)
        "topic": "...",
        "companyProfile": {"name", "businessSector", "address"},
        "campaign": {"name", "objective", "status", "plannedBudget",
                     "startDate", "endDate", "channels", "results"},
        "recentMessages": [{"sender": "USER"|"AI", "content": "..."}]
      }
    }
    -> {"answer": "..."}

    POST /ask/stream   (même corps, même en-tête)
    -> text/event-stream, la réponse au fil de sa génération :
       data: {"type": "delta", "text": "..."}   (répété)
       data: {"type": "done"}                      (fin normale)
       data: {"type": "error"}                     (échec en cours de route)
    Une erreur AVANT le premier morceau (Gemini surchargé, clé invalide...)
    reste un HTTP 503, comme /ask.

    POST /page-health/analyze  (même en-tête)
    -> bilan d'une Page Facebook (statistiques calculées par le backend) :
       {summary, strengths[], watchouts[], actions[{title, detail}]}. Voir
       page_health_analysis.py.

    POST /simulation/analyze   (même en-tête)
    -> analyse d'une simulation de campagne digitale calculée par le
       backend : {summary, strengths[], risks[], recommendations[{title,
       detail}], scenarioChoice}. Voir simulation_analysis.py.

Mode "public" : visiteur anonyme du site, relayé par l'endpoint public
(limité par IP) du backend. Prompt vitrine, aucune donnée (ni RAG sur les
documents internes, ni SQL), 500 caractères et 4 messages d'historique au
plus ; topic, companyProfile et campaign sont refusés.

Prérequis : GEMINI_API_KEY et INTERNAL_TOKEN définis, base vectorielle
Chroma construite (étape 3 du pipeline chatbot). PostgreSQL (Text-to-SQL)
est facultatif : s'il est injoignable, le chatbot répond sans les données
chiffrées.

IMPORTANT : à lancer depuis la racine du projet.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from chatbot import (
    LlmRequest,
    load_public_system_prompt,
    load_system_prompt,
    prepare_public_question,
    prepare_question,
)
from rag_retrieve import warm_up as warm_up_rag
from page_health_analysis import analyze_page_health, load_page_health_prompt
from simulation_analysis import analyze_simulation, load_simulation_prompt
from text_to_sql import get_engine, get_table_schema

# Sans configuration, Python n'affiche que les WARNING et plus : on veut aussi
# les INFO (durée des analyses) dans `docker compose logs`.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
logger = logging.getLogger("kiyanza.chatbot_api")

# Lu une seule fois au démarrage. Le service refuse de démarrer sans lui :
# exposé sur Internet sans secret, n'importe qui pourrait consommer le quota
# Gemini (§6 du canevas d'intégration backend).
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")
MIN_TOKEN_LENGTH = 32

PUBLIC_MAX_MESSAGE_LENGTH = 500
PUBLIC_MAX_RECENT_MESSAGES = 4

_system_prompt = None
_public_system_prompt = None
_simulation_prompt = None
_page_health_prompt = None


class CompanyProfile(BaseModel):
    name: str | None = None
    businessSector: str | None = None
    address: str | None = None


class CampaignContext(BaseModel):
    name: str | None = None
    objective: str | None = None
    status: str | None = None
    plannedBudget: float | str | None = None
    startDate: str | None = None
    endDate: str | None = None
    channels: list[str] = Field(default_factory=list, max_length=30)
    results: dict[str, float | int | str] = Field(default_factory=dict, max_length=30)


class RecentMessage(BaseModel):
    sender: Literal["USER", "AI"]
    content: str = Field(..., max_length=5000)


class AskContext(BaseModel):
    topic: str | None = None
    companyProfile: CompanyProfile | None = None
    campaign: CampaignContext | None = None
    recentMessages: list[RecentMessage] = Field(default_factory=list, max_length=20)


class AskRequest(BaseModel):
    mode: Literal["expert", "public"] = "expert"
    conversationId: str | None = None
    userMessage: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        examples=["Comment toucher plus de clients à Douala avec un petit budget ?"],
    )
    context: AskContext | None = None

    @model_validator(mode="after")
    def check_public_limits(self) -> "AskRequest":
        if self.mode != "public":
            return self
        if len(self.userMessage) > PUBLIC_MAX_MESSAGE_LENGTH:
            raise ValueError(f"userMessage limité à {PUBLIC_MAX_MESSAGE_LENGTH} caractères en mode public")
        ctx = self.context
        if ctx and (ctx.topic or ctx.companyProfile or ctx.campaign):
            raise ValueError("topic, companyProfile et campaign sont interdits en mode public")
        if ctx and len(ctx.recentMessages) > PUBLIC_MAX_RECENT_MESSAGES:
            raise ValueError(f"{PUBLIC_MAX_RECENT_MESSAGES} messages d'historique au plus en mode public")
        return self


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

    global _system_prompt, _public_system_prompt, _simulation_prompt, _page_health_prompt
    _system_prompt = load_system_prompt()
    _public_system_prompt = load_public_system_prompt()
    _simulation_prompt = load_simulation_prompt()
    _page_health_prompt = load_page_health_prompt()

    # Charge le modèle d'embeddings et la base Chroma dès le démarrage :
    # sinon la première question paie 10 à 20 s de chargement, et une base
    # Chroma absente ne se découvrirait qu'au premier appel.
    warm_up_rag()
    # Connexion et schéma SQL préparés d'avance. Facultatif : sans PostgreSQL
    # (ou sans la table campaigns), le chatbot répond sans données chiffrées.
    try:
        get_table_schema(get_engine())
    except Exception as e:
        logger.warning("Text-to-SQL indisponible au démarrage : %s", e)
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


UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Le chatbot est temporairement indisponible.",
)


def prepare(request: AskRequest) -> LlmRequest:
    """Recherche RAG/SQL et contexte : tout ce qui précède l'appel au LLM."""
    context = request.context or AskContext()
    recent_messages = [m.model_dump() for m in context.recentMessages]
    if request.mode == "public":
        return prepare_public_question(request.userMessage, _public_system_prompt, recent_messages)
    return prepare_question(
        request.userMessage,
        _system_prompt,
        topic=context.topic,
        company_profile=context.companyProfile.model_dump(exclude_none=True) if context.companyProfile else None,
        recent_messages=recent_messages,
        campaign=context.campaign.model_dump(exclude_none=True) if context.campaign else None,
    )


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(verify_internal_token)])
def ask(request: AskRequest):
    """Pose une question au chatbot marketing de Kiyanza."""
    try:
        answer = prepare(request).run()
    except Exception:
        # Le détail (clé API invalide, quota Gemini, Chroma corrompue...)
        # reste dans les logs du serveur : le renvoyer au client exposerait
        # des informations internes (§6.3 : informer sans divulguer).
        logger.exception("Échec du traitement de /ask (mode %s, conversation %s)", request.mode, request.conversationId)
        raise UNAVAILABLE
    return {"answer": answer}


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.post("/ask/stream", dependencies=[Depends(verify_internal_token)])
def ask_stream(request: AskRequest):
    """Même question que /ask, réponse envoyée au fil de sa génération (SSE)."""
    try:
        chunks = prepare(request).stream()
        # Le premier morceau est attendu ICI : une erreur de démarrage
        # (Gemini surchargé, clé invalide) donne un vrai 503 plutôt qu'un
        # flux 200 vide.
        first = next(chunks)
    except StopIteration:
        logger.error("Réponse Gemini vide (mode %s, conversation %s)", request.mode, request.conversationId)
        raise UNAVAILABLE
    except Exception:
        logger.exception("Échec du démarrage de /ask/stream (mode %s, conversation %s)", request.mode, request.conversationId)
        raise UNAVAILABLE

    def events() -> Iterator[str]:
        yield sse({"type": "delta", "text": first})
        try:
            for chunk in chunks:
                yield sse({"type": "delta", "text": chunk})
        except Exception:
            logger.exception("Flux interrompu (mode %s, conversation %s)", request.mode, request.conversationId)
            yield sse({"type": "error"})
            return
        yield sse({"type": "done"})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Aucun proxy intermédiaire ne doit mettre la réponse en tampon.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Analyse d'une simulation de campagne digitale (POST /simulation/analyze)
# ---------------------------------------------------------------------------


class SimulationBudget(BaseModel):
    amount: float = Field(..., gt=0)
    allocation: str | None = None


class SimulationAudience(BaseModel):
    ageMin: int | None = None
    ageMax: int | None = None
    targetGender: str | None = None
    locations: list[str] = Field(default_factory=list, max_length=20)
    interests: list[str] = Field(default_factory=list, max_length=30)


class SimulationKpis(BaseModel):
    predictedReach: float | None = None
    predictedEngagementRate: float | None = None
    predictedCtr: float | None = None
    predictedRoas: float | None = None
    avgCpc: float | None = None
    costPerAcquisition: float | None = None
    conversionRate: float | None = None
    warnings: list[str] = Field(default_factory=list, max_length=10)


class SimulationScenario(BaseModel):
    label: str
    isRecommended: bool = False
    score: float | None = None
    predictedReach: float | None = None
    predictedClicks: float | None = None
    predictedConversions: float | None = None
    predictedRoas: float | None = None


class SimulationChannel(BaseModel):
    platform: str
    budgetAmount: float | None = None
    budgetPercent: float | None = None
    predictedReach: float | None = None
    predictedClicks: float | None = None
    predictedConversions: float | None = None
    predictedRoas: float | None = None


class SimulationAnalysisRequest(BaseModel):
    """Paramètres et résultats d'une simulation, tels que calculés par le backend."""
    campaignName: str | None = None
    objective: str
    budget: SimulationBudget
    startDate: str | None = None
    endDate: str | None = None
    audience: SimulationAudience
    channels: list[str] = Field(default_factory=list, max_length=5)
    companyProfile: CompanyProfile | None = None
    results: SimulationKpis
    scenarios: list[SimulationScenario] = Field(default_factory=list, max_length=5)
    channelBreakdown: list[SimulationChannel] = Field(default_factory=list, max_length=5)


class SimulationRecommendation(BaseModel):
    title: str
    detail: str


class SimulationAnalysis(BaseModel):
    summary: str
    strengths: list[str]
    risks: list[str]
    recommendations: list[SimulationRecommendation]
    scenarioChoice: str


@app.post("/simulation/analyze", response_model=SimulationAnalysis, dependencies=[Depends(verify_internal_token)])
def simulation_analyze(request: SimulationAnalysisRequest):
    """Explique une simulation : résumé, points forts, risques, recommandations."""
    started = time.monotonic()
    try:
        analysis = analyze_simulation(request.model_dump(exclude_none=True), _simulation_prompt)
    except Exception:
        logger.exception(
            "Échec de /simulation/analyze (objectif %s) après %.1f s", request.objective, time.monotonic() - started
        )
        raise UNAVAILABLE
    logger.info("Analyse de simulation produite en %.1f s (objectif %s)", time.monotonic() - started, request.objective)
    return analysis


# ---------------------------------------------------------------------------
# Santé d'une Page Facebook (POST /page-health/analyze)
# ---------------------------------------------------------------------------


class PageHealthKpi(BaseModel):
    key: str
    current: float | None = None
    previous: float | None = None
    change: float | None = None


class PageHealthTopPost(BaseModel):
    message: str = Field("", max_length=400)
    createdTime: str
    reactions: int = 0
    comments: int = 0
    shares: int = 0


class PageHealthSlot(BaseModel):
    weekday: int = Field(..., ge=0, le=6)
    slot: int = Field(..., ge=0, le=7)
    posts: int
    avgInteractions: float


class PageHealthBestTimes(BaseModel):
    enough: bool
    sampleSize: int
    top: list[PageHealthSlot] = Field(default_factory=list, max_length=5)


class PageHealthRequest(BaseModel):
    """Indicateurs d'une Page Facebook, tels que calculés par le backend."""
    pageName: str = Field(..., max_length=200)
    followers: int | None = None
    periodDays: int = 28
    kpis: list[PageHealthKpi] = Field(default_factory=list, max_length=5)
    postsInPeriod: int = 0
    postsPerWeek: float = 0
    avgInteractionsPerPost: float | None = None
    engagementRate: float | None = None
    topPosts: list[PageHealthTopPost] = Field(default_factory=list, max_length=3)
    bestTimes: PageHealthBestTimes


class PageHealthAction(BaseModel):
    title: str
    detail: str


class PageHealthAnalysis(BaseModel):
    summary: str
    strengths: list[str]
    watchouts: list[str]
    actions: list[PageHealthAction]


@app.post("/page-health/analyze", response_model=PageHealthAnalysis, dependencies=[Depends(verify_internal_token)])
def page_health_analyze(request: PageHealthRequest):
    """Bilan d'une Page Facebook : résumé, points forts, vigilance, 3 actions."""
    started = time.monotonic()
    try:
        analysis = analyze_page_health(request.model_dump(exclude_none=True), _page_health_prompt)
    except Exception:
        logger.exception("Échec de /page-health/analyze après %.1f s", time.monotonic() - started)
        raise UNAVAILABLE
    logger.info("Bilan de Page produit en %.1f s", time.monotonic() - started)
    return analysis
