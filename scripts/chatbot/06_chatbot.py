"""
Etape 6 : le chatbot complet, mode "Poser une question", en ligne de commande.

Toute la logique reutilisable vit desormais dans chatbot.py (extrait d'ici
pour pouvoir etre importee aussi bien par ce script que par chatbot_api.py
— un fichier commencant par un chiffre ne peut pas etre importe comme
module Python).

Usage :
    python scripts/chatbot/06_chatbot.py
    (puis pose tes questions dans le terminal, Ctrl+C pour quitter)
"""

from chatbot import load_system_prompt, answer_question


def main():
    print("Chargement du system prompt et des modeles (RAG)...")
    system_prompt = load_system_prompt()

    print("Assistant Kiyanza pret. Pose ta question (Ctrl+C pour quitter).\n")
    while True:
        try:
            question = input("Toi > ").strip()
            if not question:
                continue
            answer = answer_question(question, system_prompt)
            print(f"\nKiyanza > {answer}\n")
        except KeyboardInterrupt:
            print("\nA bientot !")
            break


if __name__ == "__main__":
    main()
