"""
Etape 3 : generer les embeddings des chunks de texte (produits par le
script 01) et les stocker dans une base vectorielle locale Chroma, pour
pouvoir faire des recherches semantiques dessus (RAG).

On utilise un modele d'embeddings open-source et gratuit qui tourne en
local (sentence-transformers), adapte au francais. Pas besoin de cle API
ni de connexion internet une fois le modele telecharge la premiere fois.

Usage :
    python scripts/03_generate_embeddings.py
"""

import json
from pathlib import Path

# Doit etre fait AVANT l'import de chromadb / sentence_transformers :
#   - desactive la telemetrie chromadb (bug connu de capture() dans cette version)
#   - force le mode hors-ligne pour sentence-transformers une fois le
#     modele deja telecharge (evite les tentatives de reconnexion a
#     Hugging Face si la connexion est lente ou instable)
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

# --- Config -------------------------------------------------------------
CHUNKS_PATH = Path("output/text_chunks.json")
CHROMA_DIR = Path("output/chroma_db")          # base vectorielle persistante
COLLECTION_NAME = "kiyanza_knowledge_base"

# Modele multilingue, performant sur du francais, ~470 Mo (telecharge une
# seule fois puis mis en cache localement).
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"


def load_chunks(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} introuvable. Lance d'abord "
            f"'python scripts/01_extract_and_chunk_text.py'."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    chunks = load_chunks(CHUNKS_PATH)
    print(f"{len(chunks)} chunks charges depuis {CHUNKS_PATH}")

    print(f"Chargement du modele d'embeddings '{EMBEDDING_MODEL_NAME}'...")
    print("(le premier lancement telecharge le modele, ca peut prendre quelques minutes)")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    texts = [chunk["text"] for chunk in chunks]
    ids = [chunk["chunk_id"] for chunk in chunks]
    metadatas = [
        {"section": chunk["section"], "source": chunk["source"], "document": chunk["document"]}
        for chunk in chunks
    ]

    print("Calcul des embeddings...")
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        batch_size=32,
        normalize_embeddings=True,
    )

    print(f"Ecriture dans la base vectorielle Chroma ({CHROMA_DIR})...")
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    # On repart d'une collection propre a chaque execution du script,
    # pour eviter les doublons si tu relances apres avoir modifie tes documents.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(COLLECTION_NAME)

    collection.add(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=metadatas,
    )

    print(f"Termine. {collection.count()} chunks indexes dans la collection '{COLLECTION_NAME}'.")

    # Petit test de recherche pour verifier que tout fonctionne
    print("\n--- Test de recherche semantique ---")
    query = "Comment fonctionne le suivi des affiches publicitaires ?"
    query_embedding = model.encode([query], normalize_embeddings=True).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=3)

    print(f"Question test : {query}\n")
    for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
        print(f"[{i+1}] ({meta['document']} — {meta['section']})")
        print(doc[:200].replace("\n", " ") + "...\n")


if __name__ == "__main__":
    main()
