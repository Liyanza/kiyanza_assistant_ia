"""
Logique reutilisable de recherche RAG. Transforme une question en
embedding et recupere les chunks de texte les plus pertinents depuis la
base vectorielle Chroma construite a l'etape 3.

Importe par :
    - scripts/05_rag_retrieve.py (usage en ligne de commande, pour tester)
    - scripts/06_chatbot.py (chatbot final)
"""

from pathlib import Path

# Doit etre fait AVANT l'import de chromadb / sentence_transformers :
#   - desactive la telemetrie chromadb (bug connu de capture() dans cette version)
#   - force le mode hors-ligne pour sentence-transformers : le modele est
#     deja telecharge et mis en cache localement, inutile (et fragile en
#     cas de connexion lente) de revalider en ligne a chaque lancement.
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

CHROMA_DIR = Path("output/chroma_db")
COLLECTION_NAME = "kiyanza_knowledge_base"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"

TOP_K = 2   # nombre de chunks a recuperer par question (reduit pour la vitesse)

# Seuil de distance semantique au-dela duquel un chunk est juge non pertinent
# et donc ignore (evite d'injecter du contexte hors-sujet pour des messages
# comme "bonjour", qui n'ont pas de sens semantique fort).
# Avec des embeddings normalises et la distance L2 (metrique par defaut de
# Chroma), une distance > 1.0 correspond a une similarite cosinus < 0.5,
# ce qui est deja tres faible. A ajuster si besoin apres tests.
MAX_DISTANCE = 1.0

# Le modele et la collection sont charges une seule fois et reutilises
# entre les appels (evite de recharger le modele a chaque question).
_model = None
_collection = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = client.get_collection(COLLECTION_NAME)
    return _collection


def warm_up() -> None:
    """
    Charge le modele et la collection immediatement (appele au demarrage de
    l'API) : echoue tout de suite si la base Chroma est absente, plutot qu'a
    la premiere question d'un utilisateur.
    """
    _get_model()
    _get_collection()


def retrieve_relevant_chunks(question: str, top_k: int = TOP_K) -> list[dict]:
    """
    Renvoie une liste de chunks pertinents pour la question, chacun sous la
    forme {"text": str, "section": str, "document": str}.
    Renvoie une liste vide si aucun chunk n'est assez proche semantiquement
    (question hors-sujet, salutation, etc.) plutot que de renvoyer les
    chunks les moins mauvais quand meme.
    """
    model = _get_model()
    collection = _get_collection()

    query_embedding = model.encode([question], normalize_embeddings=True).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)

    chunks = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, distance in zip(documents, metadatas, distances):
        if distance <= MAX_DISTANCE:
            chunks.append({"text": doc, "section": meta["section"], "document": meta["document"]})

    return chunks


def format_chunks_for_prompt(chunks: list[dict]) -> str:
    """Met en forme les chunks recuperes pour les injecter dans le prompt du LLM."""
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        parts.append(f"[Extrait {i} — {chunk['document']} / {chunk['section']}]\n{chunk['text']}")
    return "\n\n".join(parts)
