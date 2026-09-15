"""
Tâches Celery du monitoring radio (Kiyanza - cahier des charges IA,
section 4.7).

Deux tâches qui travaillent ensemble :

1. check_upcoming_diffusions (tâche périodique, via Celery Beat, toutes les
   60 secondes) : regarde en base les diffusions prévues dont le moment de
   capture approche, et programme précisément capture_and_detect pour
   chacune (via apply_async(eta=...) — Celery se charge alors d'attendre
   jusqu'à l'heure exacte avant d'exécuter la tâche).

2. capture_and_detect (exécutée à l'heure programmée) : capture le flux
   radio pendant la fenêtre prévue, cherche le spot dedans, calcule l'écart
   avec l'heure prévue, enregistre le résultat en base.

Pourquoi cette séparation en deux tâches plutôt qu'une seule tâche
planifiée directement à la création de l'entrée : Celery Beat est conçu
pour des tâches périodiques régulières, pas pour programmer des milliers
de tâches ponctuelles à l'avance. Ce pattern (Beat qui surveille et
programme au fur et à mesure) est la pratique standard recommandée par
Celery pour ce genre de cas.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from celery_app import app
from radio_capture import capture_stream
from audio_detection import detect_spot_in_stream
from radio_schedule import (
    get_entries_ready_to_schedule,
    get_entry,
    mark_status,
    save_result,
)

CAPTURES_DIR = Path(__file__).resolve().parent / "captures"


@app.task(name="radio_monitoring_tasks.check_upcoming_diffusions")
def check_upcoming_diffusions():
    """
    Tâche périodique (toutes les 60s) : trouve les diffusions prévues dont
    le moment de capture approche, et programme précisément leur capture.
    """
    entries = get_entries_ready_to_schedule(lookahead_minutes=2)

    for entry in entries:
        capture_start = entry["planned_datetime"] - timedelta(minutes=entry["capture_lead_minutes"])

        # Marqué 'scheduled' IMMÉDIATEMENT pour ne pas le programmer deux
        # fois si cette tâche périodique repasse avant que la capture ait
        # commencé.
        mark_status(entry["schedule_id"], "scheduled")

        capture_and_detect.apply_async(
            args=[entry["schedule_id"]],
            eta=capture_start,
        )

    return {"scheduled_count": len(entries)}


@app.task(name="radio_monitoring_tasks.capture_and_detect", bind=True, max_retries=1)
def capture_and_detect(self, schedule_id: str):
    """
    Capture le flux radio pendant la fenêtre prévue pour cette diffusion,
    cherche le spot de référence dedans, et enregistre le résultat.
    """
    entry = get_entry(schedule_id)
    if entry is None:
        return {"error": f"Diffusion planifiée '{schedule_id}' introuvable."}

    mark_status(schedule_id, "processing")

    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CAPTURES_DIR / f"{schedule_id}.wav"

    capture_start_time = datetime.utcnow()
    capture_result = capture_stream(
        stream_url=entry["stream_url"],
        duration_seconds=entry["capture_duration_seconds"],
        output_path=str(output_path),
    )

    if not capture_result["success"]:
        save_result(
            schedule_id,
            detected=False,
            error_message=f"Échec de capture : {capture_result['error']}",
        )
        return capture_result

    detection_result = detect_spot_in_stream(
        reference_path=entry["reference_spot_path"],
        stream_path=str(output_path),
    )

    detected_at = None
    deviation_minutes = None
    if detection_result["detected"]:
        detected_at = capture_start_time + timedelta(seconds=detection_result["detected_at_seconds"])
        deviation_minutes = round((detected_at - entry["planned_datetime"]).total_seconds() / 60, 2)

    save_result(
        schedule_id,
        detected=detection_result["detected"],
        detected_at=detected_at,
        deviation_minutes=deviation_minutes,
        best_score=detection_result["best_score"],
    )

    return {
        "schedule_id": schedule_id,
        "detected": detection_result["detected"],
        "detected_at": detected_at.isoformat() if detected_at else None,
        "deviation_minutes": deviation_minutes,
    }
