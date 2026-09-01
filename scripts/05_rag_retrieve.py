"""
Etape 5 : teste la recherche RAG depuis la ligne de commande.

Usage :
    python scripts/05_rag_retrieve.py "Comment fonctionne le monitoring radio ?"
"""

import sys

from rag_retrieve import retrieve_relevant_chunks, format_chunks_for_prompt


def main():
    if len(sys.argv) < 2:
        print('Usage : python scripts/05_rag_retrieve.py "ta question ici"')
        sys.exit(1)

    question = sys.argv[1]
    chunks = retrieve_relevant_chunks(question)

    print(f"Question : {question}\n")
    print(f"{len(chunks)} extraits pertinents trouves :\n")
    print(format_chunks_for_prompt(chunks))


if __name__ == "__main__":
    main()
