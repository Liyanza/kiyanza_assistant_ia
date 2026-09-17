"""
Gestion des fichiers audio de spots publicitaires uploadés par l'utilisateur
(l'"empreinte sonore" de référence, cahier des charges IA §4.7).

Un spot est uploadé UNE FOIS (il sert de référence pour toutes les
diffusions planifiées de cette campagne radio), puis référencé par son
spot_id dans chaque entrée de scripts/radio_monitoring/radio_schedule.py.

Le fichier uploadé (quel que soit son format d'origine — mp3, wav...) est
converti via ffmpeg vers le format standard attendu par audio_detection.py
(mono, 22050 Hz, WAV), pour éviter toute surprise de format au moment de la
comparaison.
"""

import subprocess
import uuid
from pathlib import Path

SPOTS_DIR = Path(__file__).resolve().parent / "uploaded_spots"
TARGET_SAMPLE_RATE = 22050


def save_spot_file(file_bytes: bytes, original_filename: str) -> dict:
    """
    Sauvegarde un fichier audio uploadé, le convertit au format standard,
    et retourne son identifiant + chemin.

    Ne lève jamais d'exception non gérée (§6.3) : retourne un dict avec
    success=False et un message d'erreur clair si la conversion échoue
    (ex. fichier corrompu, pas un vrai fichier audio).
    """
    SPOTS_DIR.mkdir(parents=True, exist_ok=True)
    spot_id = f"SPOT-{uuid.uuid4().hex[:8].upper()}"

    original_suffix = Path(original_filename).suffix or ".bin"
    raw_path = SPOTS_DIR / f"{spot_id}_original{original_suffix}"
    final_path = SPOTS_DIR / f"{spot_id}.wav"

    raw_path.write_bytes(file_bytes)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_path),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", "1",
        "-f", "wav",
        str(final_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        raw_path.unlink(missing_ok=True)
        return {"success": False, "spot_id": None, "path": None, "error": "Conversion audio trop longue (fichier suspect)."}

    raw_path.unlink(missing_ok=True)  # on ne garde que la version convertie

    if not final_path.exists() or final_path.stat().st_size == 0:
        return {
            "success": False,
            "spot_id": None,
            "path": None,
            "error": (
                "Impossible de lire ce fichier comme un fichier audio valide. "
                f"Détail technique : {result.stderr[-300:]}"
            ),
        }

    return {"success": True, "spot_id": spot_id, "path": str(final_path), "error": None}


def get_spot_path(spot_id: str) -> str:
    """Retourne le chemin du fichier converti pour ce spot_id, ou None
    s'il n'existe pas."""
    path = SPOTS_DIR / f"{spot_id}.wav"
    return str(path) if path.exists() else None
