"""
Etape 4 : teste l'outil text-to-SQL depuis la ligne de commande.

Usage :
    python scripts/04_text_to_sql.py "Quel est le ROAS moyen des campagnes Facebook ?"
"""

import sys

from text_to_sql import answer_with_sql


def main():
    if len(sys.argv) < 2:
        print('Usage : python scripts/04_text_to_sql.py "ta question ici"')
        sys.exit(1)

    question = sys.argv[1]
    print(f"Question : {question}\n")

    result_df, sql_query = answer_with_sql(question)

    print(f"Requete SQL generee :\n{sql_query}\n")
    if result_df is not None:
        print("Resultat :")
        print(result_df)
    else:
        print("Aucun resultat exploitable (question hors-sujet ou requete jugee non sure).")


if __name__ == "__main__":
    main()
