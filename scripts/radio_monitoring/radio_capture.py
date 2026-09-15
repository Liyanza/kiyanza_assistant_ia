"""
Capture d'un flux radio en direct (ou de tout fichier/URL audio lisible par
ffmpeg) vers un fichier .wav local, prêt à être analysé par
audio_detection.py (Kiyanza - cahier des charges IA, section 4.7
"Monitoring intelligent des diffusions radio").

Utilise ffmpeg en sous-processus plutôt qu'une bibliothèque Python dédiée :
c'est l'outil le plus robuste et le plus universel pour lire des flux audio
en ligne (HTTP, Icecast/Shoutcast, HLS...), et il gère lui-même la
conversion vers le format exact attendu par notre module de détection
(mono, 22050 Hz, PCM WAV) — pas de traitement supplémentaire nécessaire.

Prérequis : ffmpeg doit être installé sur la machine et accessible dans le
PATH système (pas une bibliothèque Python — un logiciel à part entière).
Sous Windows : `winget install ffmpeg` (ou téléchargement manuel depuis
https://www.gyan.dev/ffmpeg/builds/ si winget n'est pas disponible).
"""

import subprocess
from pathlib import Path

# Doit correspondre exactement à SAMPLE_RATE dans audio_detection.py, pour
# que le fichier capturé soit directement utilisable sans re-traitement.
TARGET_SAMPLE_RATE = 22050


def capture_stream(stream_url: str, duration_seconds: int, output_path: str, timeout_margin: int = 30) -> dict:
    """
    Capture duration_seconds de flux audio depuis stream_url (URL réseau ou
    fichier local), et l'enregistre en .wav (mono, 22050 Hz) à output_path.

    timeout_margin : secondes supplémentaires accordées à ffmpeg au-delà de
    la durée demandée, pour laisser le temps à la connexion de s'établir
    avant d'abandonner (utile pour un flux réseau, moins pour un fichier
    local, mais sans danger dans les deux cas).

    Retourne un dict avec le résultat, jamais une exception non gérée
    (§6.3 du cahier des charges : signaler l'échec plutôt que planter).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    is_network_stream = stream_url.startswith("http://") or stream_url.startswith("https://")

    cmd = ["ffmpeg", "-y"]
    if is_network_stream:
        # -icy 0 : désactive les métadonnées ICY (titres de chansons insérées
        # dans le flux par le serveur Icecast/Shoutcast), qui perturbent le
        # calcul de durée de ffmpeg. Option spécifique au protocole HTTP,
        # inapplicable à un fichier local (d'où cette condition).
        cmd += ["-icy", "0"]
    cmd += [
        "-t", str(duration_seconds),           # durée à capturer — placé AVANT -i : limite la lecture de
                                                 # l'entrée elle-même, plus fiable qu'une limite en sortie
                                                 # pour un flux en direct sans durée totale connue
        "-i", stream_url,
        "-ar", str(TARGET_SAMPLE_RATE),        # ré-échantillonnage direct au bon taux
        "-ac", "1",                            # conversion en mono
        "-f", "wav",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=duration_seconds + timeout_margin,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output_path": None,
            "error": (
                f"La capture a dépassé le temps imparti "
                f"({duration_seconds + timeout_margin}s). Le flux est peut-être "
                f"injoignable ou trop lent à démarrer."
            ),
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output_path": None,
            "error": (
                "ffmpeg est introuvable sur cette machine. Installe-le "
                "(winget install ffmpeg sous Windows) et vérifie qu'il est "
                "accessible dans le PATH."
            ),
        }

    success = output_path.exists() and output_path.stat().st_size > 0

    if not success:
        return {
            "success": False,
            "output_path": None,
            "error": result.stderr[-500:] if result.stderr else "Échec de capture, raison inconnue.",
        }

    return {
        "success": True,
        "output_path": str(output_path),
        "error": None,
    }
