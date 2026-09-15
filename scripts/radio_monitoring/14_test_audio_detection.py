"""
Script CLI - Teste le module de détection audio (audio_detection.py) sur
des fichiers audio de test synthétiques, avant tout branchement sur un
vrai flux radio.

IMPORTANT : à exécuter depuis la racine du projet, avec les 4 fichiers
audio de test placés dans scripts/radio_monitoring/test_audio/.

Usage :
    python scripts/radio_monitoring/14_test_audio_detection.py
"""

import json
from pathlib import Path
from audio_detection import detect_spot_in_stream

TEST_AUDIO_DIR = Path(__file__).resolve().parent / "test_audio"

SPOT = TEST_AUDIO_DIR / "spot_reference.wav"
STREAM_WITH_SPOT = TEST_AUDIO_DIR / "stream_with_spot.wav"
STREAM_WITH_SPOT_NOISY = TEST_AUDIO_DIR / "stream_with_spot_noisy.wav"
STREAM_WITHOUT_SPOT = TEST_AUDIO_DIR / "stream_without_spot.wav"


def run_case(label: str, spot_path: Path, stream_path: Path):
    print(f"--- {label} ---")
    for path in (spot_path, stream_path):
        if not path.exists():
            print(f"   [ERREUR] Fichier introuvable : {path}")
            return
    result = detect_spot_in_stream(str(spot_path), str(stream_path))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()


def main():
    print("=" * 70)
    print("Test 1 : flux contenant le spot (attendu : détecté ~37.5s)")
    print("=" * 70)
    run_case("Flux propre", SPOT, STREAM_WITH_SPOT)

    print("=" * 70)
    print("Test 2 : flux dégradé - bruit + volume réduit (attendu : détecté ~37.5s)")
    print("=" * 70)
    run_case("Flux dégradé", SPOT, STREAM_WITH_SPOT_NOISY)

    print("=" * 70)
    print("Test 3 : flux SANS le spot (attendu : non détecté, score faible)")
    print("=" * 70)
    run_case("Flux de contrôle", SPOT, STREAM_WITHOUT_SPOT)


if __name__ == "__main__":
    main()
