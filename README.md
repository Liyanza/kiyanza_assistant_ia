# Kiyanza — Assistant IA Marketing pour les Marchés Émergents

Plateforme d'intelligence artificielle marketing conçue pour les PME des marchés émergents (Cameroun), permettant de concevoir, simuler, lancer et suivre des campagnes marketing digitales et radio — sans nécessiter d'équipe marketing dédiée.

Projet réalisé dans le cadre de l'**Orange Digital Center Summer Challenge** par l'équipe **Cosmos**.

## Équipe

| Membre | Rôle |
|---|---|
| Kanga Cedric | Chef de Projet |
| Nna Aristide | Designer UI/UX |
| Leane Yvanna (Ntakeu Leane) | Développeuse Mobile |
| Bitang Baudouin | Développeur Web |
| Foumegni Loic | IoT | Data/IA Scientist |
| Ambo'o Junette | Data / IA Scientist |


## Sommaire

- [Vue d'ensemble](#vue-densemble)
- [Fonctionnalités IA](#fonctionnalités-ia)
- [Architecture](#architecture)
- [Structure du projet](#structure-du-projet)
- [Installation](#installation)
- [Utilisation en local](#utilisation-en-local)
- [Déploiement Docker](#déploiement-docker)
- [Déploiement Render](#déploiement-render)
- [Référence des API](#référence-des-api)
- [Roadmap](#roadmap)

## Vue d'ensemble

Kiyanza centralise, au sein d'une seule plateforme, la conception de campagnes, leur simulation avant lancement, le suivi de leurs performances, la génération de recommandations et le contrôle de leur diffusion réelle sur le terrain (radio). L'Intelligence Artificielle est le moteur central de cette promesse.

Trois modules IA sont opérationnels à ce jour, chacun exposé via sa propre API :

| Module | Cahier des charges | Port (local) |
|---|---|---|
| **Chatbot** — "Poser une question" | §4.1.A | 8000 |
| **Simulation de campagne** — "Simuler avant de dépenser" | §4.4 | 8001 |
| **Monitoring radio** — diffusions publicitaires | §4.7 | 8002 |

## Fonctionnalités IA

### 1. Chatbot marketing (§4.1.A)

Un espace de discussion libre où l'utilisateur pose toute question liée au marketing et à la communication. Combine :
- **RAG** (Retrieval-Augmented Generation) sur une base de connaissances marketing (ChromaDB + embeddings multilingues)
- **Text-to-SQL** : traduit une question chiffrée ("quel canal a le meilleur ROAS ?") en requête SQL sur les données de campagnes
- **LLM** (Google Gemini) pour la rédaction de la réponse finale en français clair

### 2. Simulation de campagne (§4.4)

Avant de dépenser un budget réel, le module prédit les performances attendues d'une campagne et guide l'utilisateur vers de meilleures décisions.

- **Prédiction chiffrée** : reach, taux d'engagement, taux de clic (CTR) et retour sur investissement (ROAS), via 4 modèles XGBoost entraînés sur un jeu de données de 20 000 campagnes camerounaises
- **Explicabilité** : chaque prédiction est justifiée par comparaison aux moyennes historiques par catégorie (secteur, canal, plateforme...) — approche "rules engine", pas de boîte noire
- **Génération de texte en français clair** (Gemini) : présente toujours le résultat comme une estimation, jamais une garantie
- **Recommandations d'ajustement** : teste automatiquement des alternatives réalistes (budget, plateforme, tranche d'âge, format créatif) et ne suggère un changement que s'il apporte un gain significatif
- **Scénarios multi-plateformes** : pour un budget total et plusieurs plateformes envisagées, compare différentes répartitions budgétaires et recommande la meilleure selon l'objectif de la campagne
- **Lancement de campagne** : enregistre la campagne validée par l'utilisateur, avec un instantané de sa simulation (pour comparaison future avec les résultats réels)
- **Plan marketing et de communication** (§4.3) : génère, pour une campagne lancée, une proposition de stratégie, un calendrier d'actions et des canaux complémentaires adaptés à une petite structure

### 3. Monitoring radio (§4.7)

Surveille automatiquement la diffusion réelle des spots publicitaires sur les flux radio en ligne.

- **Détection par empreinte acoustique** : compare le spot de référence fourni par l'utilisateur au flux radio capturé, par extraction et comparaison de coefficients MFCC (robuste au bruit, sans dépendance lourde de type librosa/numba)
- **Capture de flux** : enregistrement du flux radio en direct via `ffmpeg`
- **Planification automatique** : Celery + Celery Beat déclenchent la capture et l'analyse aux heures prévues, avec une marge de tolérance
- **Rapport de conformité** (PDF et Excel) : pour chaque diffusion prévue, indique si le spot est passé, à quelle heure réelle, et l'écart avec l'heure prévue

## Architecture

- **Backend IA** : Python, FastAPI
- **Modèles prédictifs** : scikit-learn, XGBoost
- **LLM génératif** : Google Gemini API
- **RAG** : ChromaDB, Sentence-Transformers
- **Base de données** : PostgreSQL (SQLAlchemy)
- **Tâches asynchrones / planification** : Celery, Celery Beat, Redis
- **Traitement audio** : ffmpeg, NumPy, SciPy (MFCC fait-maison)
- **Génération de rapports** : ReportLab (PDF), openpyxl (Excel)
- **Conteneurisation** : Docker, Docker Compose
- **Déploiement cloud** : Render (Blueprint)

## Structure du projet

```
kiyanza_chatbot/
├── scripts/
│   ├── chatbot/              # Module 4.1.A — chatbot RAG + Text-to-SQL
│   ├── simulation/           # Module 4.4 — simulation, recommandations, plans
│   └── radio_monitoring/     # Module 4.7 — détection audio, scheduler, rapports
├── data/
│   ├── kiyanza_cameroon_pme_marketing_20k_v3.xlsx   # dataset d'entraînement
│   └── simulation/           # données préparées (train/test/schéma)
├── models/
│   └── simulation/           # modèles XGBoost entraînés (.joblib)
├── output/
│   └── chroma_db/            # base vectorielle du chatbot
├── run_api.py                 # lance l'API de simulation (port 8001)
├── run_chatbot_api.py         # lance l'API du chatbot (port 8000)
├── run_radio_api.py           # lance l'API du monitoring radio (port 8002)
├── Dockerfile                  # image de l'API de simulation
├── Dockerfile.chatbot           # image de l'API du chatbot
├── Dockerfile.radio              # image du monitoring radio (API + worker + beat)
├── docker-compose.yml          # orchestration locale des 5 services
├── render.yaml                  # déploiement cloud (Render Blueprint)
├── requirements.txt              # dépendances complètes (dev local)
├── requirements-api.txt           # dépendances image simulation
├── requirements-chatbot.txt        # dépendances image chatbot
├── requirements-radio.txt           # dépendances image monitoring radio
└── .env                              # variables d'environnement (non versionné)
```

## Installation

### Prérequis

- Python 3.11
- PostgreSQL
- Redis (pour le monitoring radio)
- ffmpeg (pour le monitoring radio)
- Une clé API Google Gemini gratuite : [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### Étapes

```bash
git clone https://github.com/Liyanza/kiyanza_assistant_ia.git
cd kiyanza_assistant_ia

python -m venv venv
venv\Scripts\activate          # Windows
python -m pip install -r requirements.txt
```

Crée un fichier `.env` à la racine :

```
GEMINI_API_KEY=ta_cle_gemini
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=kiyanza
DB_USER=postgres
DB_PASSWORD=ton_mot_de_passe
REDIS_URL=redis://localhost:6379/0
```

## Utilisation en local

Chaque module s'utilise indépendamment. Depuis la racine du projet :

**Chatbot**
```bash
python run_chatbot_api.py        # API sur http://localhost:8000/docs
```

**Simulation de campagne** — nécessite d'avoir préparé les données et entraîné les modèles une fois :
```bash
python scripts\simulation\07_prepare_simulation_data.py --source excel --excel-path data\kiyanza_cameroon_pme_marketing_20k_v3.xlsx
python scripts\simulation\08_train_simulation_models.py
python run_api.py                 # API sur http://localhost:8001/docs
```

**Monitoring radio** — nécessite 3 processus séparés :
```bash
python run_radio_api.py                                                          # API sur http://localhost:8002/docs
cd scripts/radio_monitoring && celery -A celery_app worker --loglevel=info -P solo  # worker (terminal dédié)
cd scripts/radio_monitoring && celery -A celery_app beat --loglevel=info             # scheduler (terminal dédié)
```

## Déploiement Docker

```bash
docker compose up --build
```

Lance les 5 services (chatbot, simulation, monitoring radio — API + worker + beat) dans des conteneurs séparés. PostgreSQL et Redis restent sur la machine hôte, accessibles via `host.docker.internal`.

## Déploiement Render

Le fichier `render.yaml` (Blueprint) décrit l'ensemble du déploiement cloud : 3 API web, 2 workers, une base PostgreSQL et un service Redis managés.

1. Pousser le projet sur GitHub
2. Sur [render.com](https://render.com) : **New +** → **Blueprint** → sélectionner le dépôt
3. Renseigner `GEMINI_API_KEY` lorsque demandé (jamais commité dans le dépôt)

## Référence des API

### Chatbot — `:8000`

| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/ask` | Pose une question au chatbot marketing |

Appelé uniquement par Liyanza-backend, avec le header `X-Internal-Token`
(= variable `INTERNAL_TOKEN`, 32 caractères minimum). Corps :
`{"userMessage": "...", "conversationId": "...", "context": {"topic", "companyProfile", "recentMessages"}}`
(seul `userMessage` est obligatoire) → `{"answer": "..."}`.
Déploiement AWS : [deploy/aws/README.md](deploy/aws/README.md).

### Simulation — `:8001`

| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/simulate/quick` | Prédictions rapides, sans texte généré |
| POST | `/simulate/full` | Prédictions + texte en français (LLM) |
| POST | `/simulate/recommendations` | Suggestions d'ajustement de paramètres |
| POST | `/simulate/multi-platform` | Comparaison de répartitions budgétaires |
| POST | `/campaigns/launch` | Enregistre une campagne validée |
| GET | `/campaigns/{campaign_id}/plan` | Plan marketing et de communication |

### Monitoring radio — `:8002`

| Méthode | Endpoint | Description |
|---|---|---|
| POST | `/spots` | Upload du fichier audio de référence du spot |
| POST | `/schedule` | Planifie une diffusion à surveiller |
| GET | `/schedule/{schedule_id}` | Statut d'une diffusion planifiée |
| GET | `/schedule` | Liste des diffusions (filtrable) |
| GET | `/report` | Télécharge le rapport de conformité (PDF/Excel) |

Chaque API expose aussi `/health` et une documentation interactive sur `/docs`.

## Roadmap

- **§4.5 — Analyse des performances marketing** : comparaison des résultats réels d'une campagne aux prédictions de simulation
- **§4.6 — Recommandations post-campagne** : suggestions basées sur les performances réelles observées
- **Monitoring radio — analyse concurrentielle** : part de voix entre marques, transcription et analyse du positionnement des messages publicitaires, cartographie des créneaux les moins saturés
- **QR Codes** et **suivi photo géolocalisé** des installations terrain