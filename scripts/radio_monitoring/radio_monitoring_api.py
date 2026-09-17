"""
API FastAPI du monitoring radio (Kiyanza - cahier des charges IA, section
4.7 "Monitoring intelligent des diffusions radio").

Endpoints :

- POST /spots : upload du fichier audio de référence du spot publicitaire
  (l'"empreinte sonore"). À faire UNE FOIS par spot ; le spot_id renvoyé
  est ensuite réutilisé pour planifier autant de diffusions que nécessaire.

- POST /schedule : planifie une diffusion à surveiller (station, heure
  prévue, spot de référence). Le scheduler Celery (voir
  radio_monitoring_tasks.py) se charge ensuite automatiquement de la
  capture et de la détection au bon moment.

- GET /schedule/{schedule_id} : consulte le statut/résultat d'une
  diffusion planifiée précise.

- GET /schedule : liste les diffusions planifiées, avec filtres optionnels
  par campaign_id et/ou station_name.

- GET /report : génère et renvoie en téléchargement le rapport de
  conformité (PDF ou Excel) pour une campagne/station donnée.

Prérequis : avoir créé les tables (11 pour launched_campaigns si utilisé,
et radio_schedule.create_table() pour ce module), avoir un fichier .env
valide, et — pour que les diffusions planifiées soient effectivement
traitées — avoir un worker Celery ET Celery Beat lancés en parallèle
(voir radio_monitoring_tasks.py).

IMPORTANT : à lancer depuis la racine du projet.
"""

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from radio_spots import save_spot_file, get_spot_path
from radio_schedule import create_monitoring_entry, get_entry, get_entries
from compliance_report import generate_pdf_report, generate_excel_report


class ScheduleRequest(BaseModel):
    station_name: str = Field(..., examples=["Balafon"])
    stream_url: str = Field(..., examples=["https://broadcasting-channels.com:9043/listen.mp3"])
    reference_spot_id: str = Field(..., examples=["SPOT-A1B2C3D4"])
    planned_datetime: datetime = Field(..., examples=["2026-03-15T08:05:00"])
    campaign_id: str | None = Field(default=None)
    capture_lead_minutes: int = Field(default=5, ge=0, le=60)
    capture_duration_seconds: int = Field(default=900, ge=30, le=3600)


class ScheduleResponse(BaseModel):
    schedule_id: str
    station_name: str
    planned_datetime: str
    status: str


app = FastAPI(
    title="Kiyanza - API de monitoring radio",
    description="Fonctionnalité 4.7 du cahier des charges IA : "
                 "'Monitoring intelligent des diffusions radio'.",
    version="1.0.0",
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


@app.post("/spots")
async def upload_spot(file: UploadFile = File(...)):
    """
    Upload du fichier audio de référence d'un spot publicitaire (mp3, wav,
    ou tout format lisible par ffmpeg). Retourne un spot_id à réutiliser
    pour planifier des diffusions.
    """
    file_bytes = await file.read()
    result = save_spot_file(file_bytes, file.filename)

    if not result["success"]:
        raise HTTPException(status_code=422, detail=result["error"])

    return {"spot_id": result["spot_id"]}


@app.post("/schedule", response_model=ScheduleResponse)
def schedule_diffusion(request: ScheduleRequest):
    """Planifie une diffusion à surveiller."""
    spot_path = get_spot_path(request.reference_spot_id)
    if spot_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Spot '{request.reference_spot_id}' introuvable. Utilise d'abord POST /spots.",
        )

    try:
        schedule_id = create_monitoring_entry(
            station_name=request.station_name,
            stream_url=request.stream_url,
            reference_spot_path=spot_path,
            planned_datetime=request.planned_datetime,
            campaign_id=request.campaign_id,
            capture_lead_minutes=request.capture_lead_minutes,
            capture_duration_seconds=request.capture_duration_seconds,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Impossible d'enregistrer la planification : {e}")

    return {
        "schedule_id": schedule_id,
        "station_name": request.station_name,
        "planned_datetime": request.planned_datetime.isoformat(),
        "status": "pending",
    }


@app.get("/schedule/{schedule_id}")
def get_schedule_status(schedule_id: str):
    """Consulte le statut/résultat d'une diffusion planifiée précise."""
    entry = get_entry(schedule_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Diffusion '{schedule_id}' introuvable.")
    return entry


@app.get("/schedule")
def list_schedules(
    campaign_id: str | None = Query(default=None),
    station_name: str | None = Query(default=None),
):
    """Liste les diffusions planifiées, avec filtres optionnels."""
    entries = get_entries(campaign_id=campaign_id, station_name=station_name)
    return {"count": len(entries), "entries": entries}


@app.get("/report")
def download_report(
    campaign_id: str | None = Query(default=None),
    station_name: str | None = Query(default=None),
    format: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
):
    """
    Génère et renvoie en téléchargement le rapport de conformité, au
    format PDF (défaut) ou Excel.
    """
    try:
        if format == "pdf":
            path = generate_pdf_report(campaign_id=campaign_id, station_name=station_name)
            media_type = "application/pdf"
        else:
            path = generate_excel_report(campaign_id=campaign_id, station_name=station_name)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return FileResponse(path, media_type=media_type, filename=Path(path).name)
