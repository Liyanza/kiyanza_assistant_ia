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

- POST /campaigns/launch : enregistre en base la campagne que l'utilisateur
  a EXPLICITEMENT décidé de lancer après avoir vu la simulation (conformité
  §6.6 : l'IA n'enregistre que ce que l'humain a validé, elle ne décide
  jamais elle-même). Contrairement aux deux endpoints ci-dessus, celui-ci
  écrit en base de données (table launched_campaigns).

- POST /simulate/recommendations : teste des ajustements réalistes du
  scénario (budget, plateforme, tranche d'âge, format créatif) et renvoie
  ceux qui amélioreraient significativement les résultats attendus — ou une
  liste vide si le scénario est déjà bon.

- POST /simulate/multi-platform : pour un budget total et plusieurs
  plateformes envisagées, génère 3 répartitions candidates du budget et
  indique la plus recommandée.

Prérequis : avoir exécuté les étapes 1, 2 (07, 08). Pour /simulate/full,
Ollama doit aussi être lancé. Pour /campaigns/launch, avoir exécuté
11_create_launched_campaigns_table.py et avoir un fichier .env valide.

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
from campaign_launch import launch_campaign
from campaign_recommendations import generate_recommendations
from platform_budget_scenarios import generate_multi_platform_scenarios, MIN_PLATFORMS, MAX_PLATFORMS
from communication_plan import generate_communication_plan


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


class LaunchCampaignRequest(CampaignScenario):
    """Reprend tous les champs du scénario simulé, + les informations
    propres à un vrai lancement de campagne."""

    campaign_name: str = Field(..., min_length=1, examples=["Promo Rentrée 2026"])
    # TODO : rendre obligatoire une fois le système d'authentification /
    # gestion des entreprises confirmé côté backend (voir campaign_launch.py).
    tenant_id: str | None = Field(default=None, examples=[None])


class LaunchCampaignResponse(BaseModel):
    campaign_id: str
    campaign_name: str
    status: str
    launched_at: str
    end_date: str
    predictions: dict


class RecommendationsResponse(BaseModel):
    baseline_predictions: dict
    priority_metric: str
    recommendations: list[dict]
    message: str | None


class MultiPlatformRequest(BaseModel):
    """Scénario de base (sans plateforme/canal/placement/budget, qui varient
    par plateforme testée), + les plateformes envisagées et le budget total
    à répartir entre elles."""

    industry: str = Field(..., examples=["Technology"])
    company_size: str = Field(..., examples=["Small"])
    city: str = Field(..., examples=["Douala"])
    campaign_objective: str = Field(..., examples=["Sales"])
    campaign_type: str = Field(..., examples=["Social Media Campaign"])
    target_age: str = Field(..., examples=["18-34"])
    target_gender: str = Field(..., examples=["All"])
    customer_segment: str = Field(..., examples=["SMEs"])
    creative_format: str = Field(..., examples=["Short Video"])
    content_type: str = Field(..., examples=["Promotional"])
    duration_days: int = Field(..., gt=0, le=365, examples=[30])
    platforms: list[str] = Field(
        ..., min_length=MIN_PLATFORMS, max_length=MAX_PLATFORMS,
        examples=[["Facebook", "YouTube", "Google Ads"]],
    )
    total_budget_xaf: float = Field(..., gt=0, examples=[500000])


class MultiPlatformResponse(BaseModel):
    priority_metric: str
    scenarios: list[dict]
    recommended_strategy: str


class CommunicationPlanResponse(BaseModel):
    campaign_id: str
    plan_text: str
    generated_at: str
    cached: bool


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


@app.post("/campaigns/launch", response_model=LaunchCampaignResponse)
def launch(request: LaunchCampaignRequest):
    """
    Enregistre en base la campagne que l'utilisateur a explicitement décidé
    de lancer, avec un instantané de la simulation à cet instant.

    C'est le point de décision humaine explicite (§6.6) : l'IA n'enregistre
    que ce que l'utilisateur a validé, elle ne lance jamais rien elle-même.
    """
    request_dict = request.model_dump()
    campaign_name = request_dict.pop("campaign_name")
    tenant_id = request_dict.pop("tenant_id")

    try:
        # On recalcule une dernière fois la simulation au moment du
        # lancement (au cas où l'utilisateur aurait ajusté un paramètre
        # juste avant de cliquer sur "Lancer"), pour que l'instantané
        # enregistré soit toujours cohérent avec le scénario final.
        result = predict_and_explain(request_dict)
        confirmation = launch_campaign(
            scenario=request_dict,
            campaign_name=campaign_name,
            predictions=result["predictions"],
            tenant_id=tenant_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Le module de simulation n'est pas disponible : {e}",
        )
    except Exception as e:
        # Couvre notamment une base de données injoignable ou mal configurée
        # (§6.3 : informer plutôt qu'échouer silencieusement).
        raise HTTPException(
            status_code=503,
            detail=f"Impossible d'enregistrer la campagne : {e}",
        )

    return {**confirmation, "predictions": result["predictions"]}


@app.post("/simulate/recommendations", response_model=RecommendationsResponse)
def simulate_recommendations(scenario: CampaignScenario):
    """
    Teste des ajustements réalistes du scénario (budget, plateforme, âge
    cible, format créatif) et renvoie ceux qui amélioreraient
    significativement les résultats — ou une liste vide si le scénario
    est déjà bon (aucune recommandation forcée, conformément à la demande).
    """
    try:
        result = generate_recommendations(scenario.model_dump())
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Le module de simulation n'est pas disponible : {e}",
        )
    return result


@app.post("/simulate/multi-platform", response_model=MultiPlatformResponse)
def simulate_multi_platform(request: MultiPlatformRequest):
    """
    Pour un budget total et plusieurs plateformes envisagées, génère 3
    répartitions candidates du budget entre elles et indique laquelle est
    recommandée selon l'objectif de la campagne.
    """
    request_dict = request.model_dump()
    platforms = request_dict.pop("platforms")
    total_budget_xaf = request_dict.pop("total_budget_xaf")

    try:
        result = generate_multi_platform_scenarios(request_dict, platforms, total_budget_xaf)
    except ValueError as e:
        # Ex. moins de 2 plateformes ou plus de 6 (déjà filtré par Pydantic
        # normalement, mais on reste défensif si generate_multi_platform_scenarios
        # est appelé avec d'autres bornes à l'avenir).
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Le module de simulation n'est pas disponible : {e}",
        )
    return result


@app.get("/campaigns/{campaign_id}/plan", response_model=CommunicationPlanResponse)
def get_communication_plan(campaign_id: str):
    """
    Renvoie le plan marketing et de communication (§4.3) d'une campagne déjà
    lancée. Généré au premier appel (via le LLM), puis servi depuis le cache
    en base pour les appels suivants (cached=true).
    """
    try:
        result = generate_communication_plan(campaign_id)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Le service de génération du plan est indisponible : {e}",
        )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune campagne trouvée avec l'identifiant '{campaign_id}'.",
        )

    return result
