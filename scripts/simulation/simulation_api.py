"""
API FastAPI - Étape 5 du module "Simuler avant de dépenser" (Kiyanza).

Expose la simulation de campagne au frontend (Web PME React / App mobile
Flutter) via deux endpoints :

- POST /simulate/quick : prédictions + facteurs explicatifs bruts, SANS appel
  au LLM. Rapide (quelques millisecondes après le premier appel), pensé pour
  être rappelé à chaque fois que l'utilisateur modifie un paramètre du
  formulaire (budget, canal, cible...) — conforme à l'exigence §4.4 du
  cahier des charges ("la simulation doit être recalculée si l'utilisateur
  modifie un paramètre") sans bloquer l'interface (§6.2 : usage fluide).

- POST /simulate/full : la même chose, PLUS le texte final rédigé en
  français clair par le LLM (étape 4). Plus lent (appel LLM = quelques
  secondes), à utiliser quand l'utilisateur veut voir l'explication
  complète (ex. un bouton "Voir l'analyse détaillée"), pas à chaque
  frappe/glissement de curseur.

Prérequis : avoir exécuté les étapes 1, 2 (07, 08). Pour /simulate/full,
Ollama doit aussi être lancé.

IMPORTANT : à lancer depuis la racine du projet.

Usage (développement local) :
    python run_api.py

    (lance le serveur sur http://localhost:8001, avec rechargement
    automatique à chaque modification du code)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from simulation_explain import predict_and_explain, load_artifacts
from simulation_text import generate_simulation_text


class CampaignScenario(BaseModel):
    """Un scénario de campagne, tel que produit par le wizard 'Créer une
    campagne' (étapes 4.2 / 4.3 du cahier des charges)."""

    industry: str = Field(..., examples=["Technology"])
    company_size: str = Field(..., examples=["Small"])
    city: str = Field(..., examples=["Douala"])
    campaign_objective: str = Field(..., examples=["Sales"])
    campaign_type: str = Field(..., examples=["Social Media Campaign"])
    channel: str = Field(..., examples=["Social Media"])
    platform: str = Field(..., examples=["Instagram"])
    placement: str = Field(..., examples=["Feed"])
    target_age: str = Field(..., examples=["18-34"])
    target_gender: str = Field(..., examples=["All"])
    customer_segment: str = Field(..., examples=["SMEs"])
    creative_format: str = Field(..., examples=["Short Video"])
    content_type: str = Field(..., examples=["Promotional"])
    duration_days: int = Field(..., gt=0, le=365, examples=[30])
    budget_xaf: float = Field(..., gt=0, examples=[500000])


class SimulationQuickResponse(BaseModel):
    predictions: dict
    explanations: dict
    warnings: list[str]


class SimulationFullResponse(SimulationQuickResponse):
    text: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Précharge les modèles + données au démarrage du serveur plutôt qu'à
    # la première requête, pour que le tout premier utilisateur n'attende
    # pas les ~4 secondes de chargement initial.
    load_artifacts()
    yield


app = FastAPI(
    title="Kiyanza - API de simulation de campagne",
    description="Fonctionnalité 4.4 du cahier des charges IA : "
                 "'Simuler avant de dépenser'.",
    version="1.0.0",
    lifespan=lifespan,
)

# En développement, on autorise toutes les origines pour simplifier les
# tests depuis le frontend local. À restreindre à l'URL réelle du frontend
# avant mise en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/simulate/quick", response_model=SimulationQuickResponse)
def simulate_quick(scenario: CampaignScenario):
    """
    Prédictions + facteurs explicatifs, sans texte LLM. À appeler à chaque
    modification d'un paramètre du formulaire de campagne.
    """
    try:
        result = predict_and_explain(scenario.model_dump())
    except FileNotFoundError as e:
        # §6.3 : informer l'utilisateur plutôt que d'échouer silencieusement
        raise HTTPException(
            status_code=503,
            detail=f"Le module de simulation n'est pas disponible : {e}",
        )
    return result


@app.post("/simulate/full", response_model=SimulationFullResponse)
def simulate_full(scenario: CampaignScenario):
    """
    Prédictions + facteurs explicatifs + texte final en français clair
    (appel LLM). À utiliser pour l'affichage détaillé, pas à chaque
    modification de paramètre (plus lent).
    """
    try:
        result = generate_simulation_text(scenario.model_dump())
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Le module de simulation n'est pas disponible : {e}",
        )
    except Exception as e:
        # Couvre notamment le cas où Ollama n'est pas lancé (erreur de
        # connexion levée par requests dans llm_client.py).
        raise HTTPException(
            status_code=503,
            detail=f"Le service de génération de texte est indisponible : {e}",
        )
    return result
