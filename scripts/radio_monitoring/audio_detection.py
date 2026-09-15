"""
Détection d'un spot publicitaire connu dans un flux audio, par comparaison
d'empreintes acoustiques (Kiyanza - cahier des charges IA, section 4.7
"Monitoring intelligent des diffusions radio").

Principe (proche de la technologie Shazam, mais volontairement simplifié
car on cherche UN spot connu dans UN flux, pas une chanson dans une base de
millions de titres) :

1. On extrait des caractéristiques acoustiques (MFCC — Mel-Frequency
   Cepstral Coefficients, standard en traitement audio, robuste au bruit et
   à la qualité variable) du spot de référence ET du flux à analyser.
2. On fait glisser une fenêtre de la taille du spot sur tout le flux, et on
   calcule à chaque position une similarité entre les empreintes.
3. Le ou les pics de similarité au-dessus d'un seuil indiquent une
   diffusion détectée, avec son horodatage exact dans le flux.

IMPORTANT — implémentation volontairement sans librosa/numba : la politique
de sécurité Windows (AppLocker/WDAC) rencontrée sur ce projet bloque
plusieurs bibliothèques compilées tierces (pyarrow, numba...). Pour éviter
ce problème récurrent, le calcul des MFCC est ici réimplémenté à la main
avec seulement numpy et scipy, déjà utilisés sans souci ailleurs dans le
projet (scikit-learn, xgboost en dépendent).

Limite de cette implémentation : ne lit que des fichiers .wav (PCM). Ce
n'est pas une contrainte pratique, puisque l'étape de capture du flux
(ffmpeg) convertira de toute façon systématiquement vers ce format avant
analyse.
"""

import numpy as np
import scipy.io.wavfile as wavfile
import scipy.signal
import scipy.fftpack

SAMPLE_RATE = 22050    # fréquence d'échantillonnage standard pour l'analyse
N_MFCC = 20             # nombre de coefficients acoustiques gardés par segment
N_MEL_FILTERS = 26      # nombre de filtres Mel (valeur standard en traitement audio)
FRAME_LENGTH = 2048     # taille de la fenêtre d'analyse (~93ms à 22050Hz)
HOP_LENGTH = 512        # pas entre deux analyses successives (~23ms à 22050Hz)

DEFAULT_DETECTION_THRESHOLD = 0.45


def load_audio(path: str) -> np.ndarray:
    """
    Charge un fichier .wav, le convertit en mono, en float32 normalisé
    entre -1 et 1, et le rééchantillonne à SAMPLE_RATE si nécessaire.
    """
    sr, data = wavfile.read(path)

    if data.ndim > 1:
        data = data.mean(axis=1)  # plusieurs canaux -> mono

    if np.issubdtype(data.dtype, np.integer):
        max_value = np.iinfo(data.dtype).max
        data = data.astype(np.float32) / max_value
    else:
        data = data.astype(np.float32)

    if sr != SAMPLE_RATE:
        n_samples = int(len(data) * SAMPLE_RATE / sr)
        data = scipy.signal.resample(data, n_samples)

    return data.astype(np.float32)


def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + hz / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def _build_mel_filterbank(n_filters: int, n_fft: int, sample_rate: int) -> np.ndarray:
    """Construit la banque de filtres Mel (triangulaires), standard en
    traitement du son — c'est ce que fait librosa en interne, ici recodé
    à la main avec seulement numpy."""
    fmin, fmax = 0.0, sample_rate / 2.0
    mel_points = np.linspace(_hz_to_mel(fmin), _hz_to_mel(fmax), n_filters + 2)
    hz_points = _mel_to_hz(mel_points)
    bin_points = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)

    filters = np.zeros((n_filters, n_fft // 2 + 1))
    for i in range(1, n_filters + 1):
        left, center, right = bin_points[i - 1], bin_points[i], bin_points[i + 1]
        if center > left:
            filters[i - 1, left:center] = (np.arange(left, center) - left) / (center - left)
        if right > center:
            filters[i - 1, center:right] = (right - np.arange(center, right)) / (right - center)
    return filters


_MEL_FILTERBANK = _build_mel_filterbank(N_MEL_FILTERS, FRAME_LENGTH, SAMPLE_RATE)
_WINDOW = np.hamming(FRAME_LENGTH)


def extract_fingerprint(audio: np.ndarray) -> np.ndarray:
    """
    Extrait l'empreinte acoustique (MFCC) d'un segment audio, calculée à la
    main (fenêtrage -> FFT -> filtres Mel -> log -> DCT), sans librosa.
    Retourne une matrice (N_MFCC x nombre_de_frames), normalisée pour que
    la comparaison ne dépende pas du volume sonore absolu.
    """
    n_frames = 1 + (len(audio) - FRAME_LENGTH) // HOP_LENGTH
    if n_frames <= 0:
        return np.zeros((N_MFCC, 0))

    mfcc_frames = np.zeros((N_MFCC, n_frames))
    for i in range(n_frames):
        start = i * HOP_LENGTH
        frame = audio[start:start + FRAME_LENGTH] * _WINDOW
        power_spectrum = np.abs(np.fft.rfft(frame, n=FRAME_LENGTH)) ** 2
        mel_energies = _MEL_FILTERBANK @ power_spectrum
        log_mel_energies = np.log(mel_energies + 1e-10)
        mfcc = scipy.fftpack.dct(log_mel_energies, type=2, norm="ortho")[:N_MFCC]
        mfcc_frames[:, i] = mfcc

    mean = mfcc_frames.mean(axis=1, keepdims=True)
    std = mfcc_frames.std(axis=1, keepdims=True) + 1e-8
    return (mfcc_frames - mean) / std


def _sliding_similarity(reference_fp: np.ndarray, stream_fp: np.ndarray) -> np.ndarray:
    """
    Calcule la similarité (corrélation normalisée) entre l'empreinte de
    référence et chaque position possible dans l'empreinte du flux.
    """
    ref_len = reference_fp.shape[1]
    stream_len = stream_fp.shape[1]
    n_positions = stream_len - ref_len + 1

    if n_positions <= 0:
        return np.array([])

    scores = np.zeros(n_positions)
    ref_flat = reference_fp.flatten()
    ref_norm = np.linalg.norm(ref_flat)

    for start in range(n_positions):
        window = stream_fp[:, start:start + ref_len].flatten()
        window_norm = np.linalg.norm(window)
        if ref_norm == 0 or window_norm == 0:
            scores[start] = 0.0
        else:
            scores[start] = np.dot(ref_flat, window) / (ref_norm * window_norm)

    return scores


def detect_spot_in_stream(
    reference_path: str,
    stream_path: str,
    threshold: float = DEFAULT_DETECTION_THRESHOLD,
) -> dict:
    """
    Cherche le spot de référence dans le flux audio, et retourne s'il a été
    détecté, à quel(s) instant(s), et avec quel score de confiance.
    """
    reference_audio = load_audio(reference_path)
    stream_audio = load_audio(stream_path)

    reference_fp = extract_fingerprint(reference_audio)
    stream_fp = extract_fingerprint(stream_audio)

    scores = _sliding_similarity(reference_fp, stream_fp)

    if len(scores) == 0:
        return {
            "detected": False,
            "best_score": 0.0,
            "detected_at_seconds": None,
            "all_peaks_seconds": [],
        }

    seconds_per_frame = HOP_LENGTH / SAMPLE_RATE
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])

    above_threshold = np.where(scores >= threshold)[0]
    peaks = []
    if len(above_threshold) > 0:
        groups = np.split(above_threshold, np.where(np.diff(above_threshold) > 10)[0] + 1)
        for group in groups:
            peak_idx = group[np.argmax(scores[group])]
            peaks.append(float(round(peak_idx * seconds_per_frame, 2)))

    return {
        "detected": best_score >= threshold,
        "best_score": round(best_score, 4),
        "detected_at_seconds": float(round(best_idx * seconds_per_frame, 2)) if best_score >= threshold else None,
        "all_peaks_seconds": peaks,
    }
