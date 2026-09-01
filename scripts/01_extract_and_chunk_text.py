"""
Etape 1 : extraire le texte des documents de reference du projet Kiyanza
(document de cadrage + cahier des charges IA) et les decouper en "chunks"
reutilisables plus tard pour le RAG.

Usage :
    python scripts/01_extract_and_chunk_text.py
"""

import json
import re
from pathlib import Path

from pypdf import PdfReader
import tiktoken

# --- Config -----------------------------------------------------------
DATA_DIR = Path("data")
OUTPUT_PATH = Path("output/text_chunks.json")

CHUNK_SIZE_TOKENS = 400      # taille cible d'un chunk (en tokens)
CHUNK_OVERLAP_TOKENS = 60    # chevauchement entre deux chunks consecutifs

# Chaque document de reference a sa propre liste de titres de sections,
# dans l'ordre ou ils apparaissent, pour etiqueter correctement les chunks.
# Ajoute une entree ici pour chaque nouveau document que tu places dans data/.
DOCUMENTS = {
    "kiyanza_cadrage.pdf": {
        "doc_label": "Document de cadrage",
        "sections": [
            "CONTEXTE",
            "PROBLEMATIQUE IDENTIFIEE",
            "PRESENTATION DE LA SOLUTION",
            "OBJECTIFS",
            "FONCTIONNALITES",
            "USER PERSONAS",
            "ETUDE DE L'EXISTANT",
            "CONCLUSION",
        ],
    },
    "kiyanza_cahier_des_charges_ia.pdf": {
        "doc_label": "Cahier des charges IA",
        "sections": [
            "1. Objet du document",
            "2. Rappel du contexte du projet",
            "3. Objectifs de la partie Intelligence Artificielle",
            "4. Périmètre fonctionnel de l'IA",
            "4.1. Assistant IA marketing",
            "4.2. Assistant IA marketing",
            "4.3. Génération d'un plan marketing",
            "4.4. Simulation de campagne",
            "4.5. Analyse des performances marketing",
            "4.6. Génération de recommandations marketing",
            "4.7. Monitoring intelligent des diffusions radio",
            "5. Fonctionnalité connexe",
            "6. Exigences non fonctionnelles",
            "7. Contraintes et hypothèses",
            "8. Utilisateurs cibles de la partie IA",
            "9. Livrables attendus",
            "10. Critères d'acceptation",
            "11. Glossaire",
        ],
    },
}

encoding = tiktoken.get_encoding("cl100k_base")


def extract_full_text(pdf_path: Path) -> str:
    """Extrait tout le texte du PDF, page par page."""
    reader = PdfReader(str(pdf_path))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text)


def split_into_sections(full_text: str, section_titles: list[str]) -> list[dict]:
    """
    Coupe le texte en grandes sections en se basant sur les titres connus.
    Renvoie une liste de {"section": str, "text": str}.
    """
    pattern = "|".join(re.escape(t) for t in section_titles)
    matches = list(re.finditer(pattern, full_text))

    sections = []
    for i, match in enumerate(matches):
        section_title = match.group()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        section_text = full_text[start:end].strip()
        if section_text:
            sections.append({"section": section_title, "text": section_text})
    return sections


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Decoupe un texte en chunks de taille ~chunk_size tokens, avec overlap."""
    tokens = encoding.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(encoding.decode(chunk_tokens))
        if end == len(tokens):
            break
        start = end - overlap  # on recule un peu pour l'overlap
    return chunks


def build_chunks_for_document(pdf_path: Path, doc_label: str, section_titles: list[str]) -> list[dict]:
    full_text = extract_full_text(pdf_path)
    sections = split_into_sections(full_text, section_titles)

    chunks = []
    for section in sections:
        pieces = chunk_text(section["text"], CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS)
        for piece in pieces:
            chunks.append({
                "section": section["section"],
                "text": piece.strip(),
                "source": pdf_path.name,
                "document": doc_label,
            })
    return chunks


def main():
    all_chunks = []

    for filename, meta in DOCUMENTS.items():
        pdf_path = DATA_DIR / filename
        if not pdf_path.exists():
            print(f"[ATTENTION] Fichier introuvable, ignore : {pdf_path.resolve()}")
            continue

        doc_chunks = build_chunks_for_document(pdf_path, meta["doc_label"], meta["sections"])
        all_chunks.extend(doc_chunks)
        print(f"{meta['doc_label']} ({filename}) -> {len(doc_chunks)} chunks")

    # On attribue les chunk_id une fois tous les documents traites,
    # pour avoir un identifiant unique global.
    for i, chunk in enumerate(all_chunks):
        chunk["chunk_id"] = f"chunk_{i:04d}"

    if not all_chunks:
        raise RuntimeError(
            "Aucun chunk genere. Verifie que tes PDF sont bien places dans data/ "
            "avec les noms attendus (voir dictionnaire DOCUMENTS dans ce script)."
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"\nTotal : {len(all_chunks)} chunks generes -> {OUTPUT_PATH}")
    print("\nExemple de chunk :")
    print(json.dumps(all_chunks[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
