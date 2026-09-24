# Déployer le chatbot sur AWS (EC2)

Ce guide met en ligne l'API du chatbot (`POST /ask`) sur une instance EC2,
en HTTPS, pour qu'elle soit appelée par Liyanza-backend. Le LLM reste
Gemini (palier gratuit) : AWS n'héberge que l'API, la base vectorielle et
PostgreSQL.

```
App web / mobile ──► Liyanza-backend (Render, JWT) ──HTTPS + X-Internal-Token──► EC2
                                                                                 ├─ caddy        (ports 80/443, certificat automatique)
                                                                                 ├─ chatbot-api  (FastAPI, port 8000 interne)
                                                                                 └─ db           (PostgreSQL, rôle lecture seule)
```

Durée : environ 45 minutes, dont 10 à 15 minutes de build Docker.

## 1. Avant de commencer

- Une clé Gemini : <https://aistudio.google.com/apikey>.
- Dans la console AWS, **Billing and Cost Management → Budgets → Create
  budget** : un budget mensuel de 10 $ avec une alerte e-mail à 80 %. C'est
  le seul garde-fou contre une facture surprise.
- Choisis une région proche de tes utilisateurs et de Render. Pour le
  Cameroun, `eu-west-3` (Paris) ou `eu-central-1` (Francfort).

## 2. Lancer l'instance

**EC2 → Instances → Launch instances** :

| Champ | Valeur |
|---|---|
| Name | `kiyanza-chatbot` |
| AMI | Ubuntu Server 24.04 LTS, architecture **64-bit (x86)** |
| Instance type | `t3.small` (2 Go de RAM). Si le build ou le démarrage manque de mémoire : `c7i-flex.large` (4 Go). Pas `t3.micro` : 1 Go ne suffit pas pour le modèle d'embeddings. Vérifie le badge « Free tier eligible » selon ton compte. |
| Key pair | Create new key pair → `kiyanza`, type ED25519, format `.pem`. Garde le fichier. |
| Network settings → Edit | Security group `kiyanza-chatbot-sg` avec 3 règles : **SSH (22)** source *My IP* ; **HTTP (80)** source *Anywhere* ; **HTTPS (443)** source *Anywhere*. N'ouvre **pas** le port 8000 ni 5432. |
| Storage | **30 Go gp3** |

Puis **EC2 → Elastic IPs → Allocate**, et **Associate** l'adresse à
l'instance. Sans elle, l'IP publique change à chaque arrêt/redémarrage, et
il faudrait reconfigurer le backend à chaque fois. Coût : environ 3,6 $/mois,
pris sur les crédits.

## 3. Préparer le serveur

Depuis ton PC (PowerShell ou Git Bash), dans le dossier du `.pem` :

```bash
ssh -i kiyanza.pem ubuntu@<ELASTIC_IP>
```

Sur le serveur :

```bash
# 4 Go de swap : le build (PyTorch + embeddings) dépasse les 2 Go d'une t3.small
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker + plugin compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

Reconnecte-toi (`ssh -i kiyanza.pem ubuntu@<ELASTIC_IP>`) pour que le groupe
`docker` soit pris en compte, puis vérifie : `docker compose version`.

## 4. Récupérer le code (dépôt privé)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub
```

Copie la clé affichée dans GitHub : **kiyanza_assistant_ia → Settings →
Deploy keys → Add deploy key** (lecture seule, ne coche pas *Allow write
access*). Puis :

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
EOF
git clone git@github.com:Liyanza/kiyanza_assistant_ia.git
cd kiyanza_assistant_ia
```

## 5. Configurer

```bash
cp .env.example .env
openssl rand -hex 32   # -> INTERNAL_TOKEN
openssl rand -hex 16   # -> DB_ADMIN_PASSWORD
openssl rand -hex 16   # -> DB_READONLY_PASSWORD
nano .env
```

Remplis au minimum :

```
GEMINI_API_KEY=<ta clé Gemini>
INTERNAL_TOKEN=<64 caractères hex>
PUBLIC_HOST=<ELASTIC_IP avec des tirets>.sslip.io
DB_ADMIN_PASSWORD=<32 caractères hex>
DB_READONLY_PASSWORD=<32 caractères hex, différent>
```

`PUBLIC_HOST` : pour l'IP `13.37.1.2`, écris `13-37-1-2.sslip.io`. Ce nom
gratuit pointe vers ton IP, ce qui permet à Caddy d'obtenir un certificat
HTTPS Let's Encrypt sans acheter de domaine. Si tu as un domaine, crée un
enregistrement A (ex: `ia.kiyanza.com`) vers l'Elastic IP et mets-le ici.

Garde `INTERNAL_TOKEN` de côté : c'est la valeur à reporter dans
`IA_SERVICE_INTERNAL_TOKEN` côté backend.

## 6. Construire et démarrer

```bash
docker compose -f docker-compose.aws.yml up -d --build
```

Le premier build prend 10 à 15 minutes (PyTorch, modèle d'embeddings,
construction de la base Chroma). Ensuite, charge les données de campagnes
pour le Text-to-SQL (une seule fois) :

```bash
docker compose -f docker-compose.aws.yml --profile tools run --rm data-loader
```

Vérifie que tout tourne :

```bash
docker compose -f docker-compose.aws.yml ps
docker compose -f docker-compose.aws.yml logs -f chatbot-api   # Ctrl+C pour quitter
```

`chatbot-api` doit afficher `Application startup complete`, et être
`healthy` dans `ps` après environ 2 minutes.

## 7. Tester depuis ton PC

```bash
# 1) En ligne, HTTPS valide -> {"status":"ok"}
curl https://<PUBLIC_HOST>/health

# 2) Sans token -> 401 (le service est bien protégé)
curl -i -X POST https://<PUBLIC_HOST>/ask -H "Content-Type: application/json" -d '{"userMessage":"test"}'

# 3) Vraie question -> {"answer":"..."}
curl -X POST https://<PUBLIC_HOST>/ask \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: <INTERNAL_TOKEN>" \
  -d '{"userMessage":"Quel canal a le meilleur ROAS en moyenne ?","context":{"companyProfile":{"name":"Test SARL","businessSector":"Agroalimentaire","address":"Douala"}}}'
```

Sous PowerShell, utilise `curl.exe` au lieu de `curl`.

## 8. Brancher le backend

Dans Render → service `liyanza-backend` → **Environment** :

```
IA_SERVICE_URL=https://<PUBLIC_HOST>
IA_SERVICE_INTERNAL_TOKEN=<la même valeur que INTERNAL_TOKEN>
```

Render redéploie. Test de bout en bout : sur l'app web, connecte-toi avec un
compte ADMIN ou MARKETING_MANAGER, ouvre le widget de chat et pose une
question. La réponse doit être du vrai texte, plus « Mock response ». (Le
Swagger du backend n'est exposé qu'hors production, sur `/docs`.)

## Exploitation

| Besoin | Commande (dans `~/kiyanza_assistant_ia`) |
|---|---|
| Déployer une nouvelle version | `git pull && docker compose -f docker-compose.aws.yml up -d --build` |
| Voir les erreurs | `docker compose -f docker-compose.aws.yml logs --tail 100 chatbot-api` |
| Redémarrer | `docker compose -f docker-compose.aws.yml restart chatbot-api` |
| Changer le token | modifier `.env`, puis `docker compose -f docker-compose.aws.yml up -d` (et mettre à jour Render) |
| Libérer de l'espace disque | `docker image prune -f` |

Les conteneurs redémarrent seuls après un reboot (`restart: unless-stopped`).
Pour économiser les crédits entre deux sessions de test : **EC2 → Instance
state → Stop** (le disque et l'Elastic IP restent facturés, quelques
centimes par jour), puis **Start** : tout redémarre automatiquement.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| Le build s'arrête avec `Killed` | Mémoire insuffisante : vérifie le swap (`free -h`), ou passe en `c7i-flex.large`. |
| `curl /health` : erreur de certificat ou timeout | Ports 80/443 fermés dans le security group, ou `PUBLIC_HOST` ne correspond pas à l'IP. Voir `docker compose ... logs caddy`. |
| `chatbot-api` redémarre en boucle | Lire `logs chatbot-api` : `INTERNAL_TOKEN` trop court (< 32), ou clé Gemini absente. |
| `/ask` renvoie 503 | Voir les logs : clé Gemini invalide ou quota gratuit atteint. |
| Les réponses ignorent les chiffres de campagnes | Données non chargées : relancer l'étape `data-loader`. |
| Le backend répond 500 « Failed to get response from AI engine » | Voir les logs Render : `IA service responded 401` = tokens différents ; `unreachable` = instance arrêtée ou mauvaise URL. |
