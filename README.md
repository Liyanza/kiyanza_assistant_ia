# Kiyanza chatbot — préparation des données (étape 1)

## 1. Ouvrir le projet dans VS Code

Ouvre le dossier `kiyanza-chatbot` dans VS Code (`File > Open Folder...`).
Ouvre un terminal intégré : `Terminal > New Terminal`.

## 2. Créer et activer un environnement virtuel Python

```bash
python -m venv venv
```

Puis active-le :
- **Windows (PowerShell)** : `venv\Scripts\Activate.ps1`
- **Windows (cmd)** : `venv\Scripts\activate.bat`
- **macOS / Linux** : `source venv/bin/activate`

Dans VS Code, sélectionne aussi cet interpréteur : `Ctrl+Shift+P` (ou `Cmd+Shift+P`)
→ "Python: Select Interpreter" → choisis celui dans `venv`.

## 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

## 4. Placer tes fichiers de données

Copie tes trois fichiers dans le dossier `data/` :
- `data/kiyanza_cadrage.pdf` (le document de cadrage)
- `data/kiyanza_cahier_des_charges_ia.pdf` (le cahier des charges du module IA)
- `data/kiyanza_cameroon_pme_marketing_20k_v2.xlsx` (le fichier Excel)

## 5. Configurer la connexion PostgreSQL

Copie `.env.example` en `.env` :

```bash
cp .env.example .env      # macOS / Linux
copy .env.example .env    # Windows
```

Ouvre `.env` et remplis avec tes vrais identifiants PostgreSQL.

Crée la base de données (si ce n'est pas déjà fait), depuis un terminal `psql`
ou pgAdmin :

```sql
CREATE DATABASE kiyanza;
```

## 6. Lancer l'extraction et le découpage du texte (RAG)

```bash
python scripts/01_extract_and_chunk_text.py
```

Ça va créer `output/text_chunks.json` : une liste de morceaux de texte,
chacun avec sa section d'origine. C'est ce fichier qu'on utilisera à
l'étape suivante pour générer les embeddings.

## 7. Charger le fichier Excel dans PostgreSQL

```bash
python scripts/02_load_excel_to_postgres.py
```

Ça va créer une table `campaigns` dans ta base PostgreSQL avec les
20 000 lignes de campagnes, prête à être interrogée en SQL.

Tu peux vérifier avec `psql` ou pgAdmin :

```sql
SELECT company, industry, roas FROM campaigns LIMIT 5;
```

## 7. Générer les embeddings et construire la base vectorielle

```bash
python scripts/03_generate_embeddings.py
```

Ce script :
- charge `output/text_chunks.json` (généré à l'étape précédente),
- calcule un embedding pour chaque chunk avec un modèle open-source
  multilingue (`paraphrase-multilingual-mpnet-base-v2`, adapté au
  français, gratuit, tourne en local),
- stocke le tout dans une base vectorielle **Chroma** persistante, dans
  `output/chroma_db/`,
- termine par un petit test de recherche sémantique pour vérifier que ça
  fonctionne.

**Premier lancement** : le modèle (~470 Mo) doit être téléchargé, ça peut
prendre quelques minutes selon ta connexion. Les lancements suivants sont
rapides.

## 8. Le system prompt de l'assistant

Le fichier `scripts/system_prompt.md` contient le prompt système de
l'assistant IA (mode « Poser une question »), rédigé directement à partir
des règles de gestion et exigences non fonctionnelles du Cahier des
charges IA (sections 4.1 et 6) : ton d'expert marketing, règles de
confidentialité entre entreprises, adaptation au contexte local,
présentation systématique de la fonctionnalité Kiyanza pertinente, etc.

## 9. Installer et tester Ollama (LLM local et gratuit)

1. Télécharge et installe Ollama : https://ollama.com/download
2. Télécharge un modèle (Mistral, bon niveau en français) :
   ```bash
   ollama pull mistral
   ```
3. Teste-le en ligne de commande :
   ```bash
   ollama run mistral
   ```
   Pose une question, vérifie que ça répond, puis `/bye` pour quitter.

Ollama tourne en arrière-plan et expose une API locale sur
`http://localhost:11434`, utilisée par nos scripts Python.

## 10. Construire l'outil text-to-SQL

```bash
python scripts/04_text_to_sql.py "Quel est le budget moyen des campagnes ?"
```

Ce script convertit ta question en requête SQL via le LLM local, l'exécute
sur la table `campaigns`, et affiche le résultat. La logique réutilisable
est dans `scripts/text_to_sql.py` (importée aussi par le chatbot final).

Sécurité intégrée : seules les requêtes `SELECT` sont autorisées ; toute
requête contenant `INSERT`, `UPDATE`, `DELETE`, `DROP`, etc. est rejetée
avant exécution.

## 11. Tester la recherche RAG

```bash
python scripts/05_rag_retrieve.py "Comment fonctionne le monitoring radio ?"
```

Récupère les extraits de documents les plus pertinents pour la question,
depuis la base Chroma construite à l'étape 7. Logique réutilisable dans
`scripts/rag_retrieve.py`.

## 12. Lancer le chatbot complet

```bash
python scripts/06_chatbot.py
```

Assemble tout : system prompt + recherche RAG (toujours) + requête SQL (si
la question semble porter sur des données chiffrées de campagnes, détecté
par une liste de mots-clés simple) + appel au LLM local pour la réponse
finale. Pose tes questions directement dans le terminal.

**Limite actuelle à connaître** : le routage RAG/SQL est une heuristique
par mots-clés, volontairement simple pour ce stade du projet. Si les
questions financières/chiffrées ne sont pas bien détectées, on pourra
remplacer cette liste par un routage décidé par le LLM lui-même dans une
prochaine itération.
