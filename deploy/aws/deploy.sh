#!/bin/sh
# Reconstruit et relance le chatbot avec le code déjà extrait dans
# ~/kiyanza_assistant_ia, puis attend que l'API soit « healthy ». Lancé par
# le workflow « Deploy (AWS) » (via Session Manager, en root) juste après la
# mise à jour du code ; utilisable aussi à la main.
#
# En cas d'échec, les derniers journaux de l'API sont affichés et le script
# sort en erreur, ce qui fait échouer le workflow.
set -eu

cd "$(dirname "$0")/../.."
COMPOSE="docker compose -f docker-compose.aws.yml"

$COMPOSE up -d --build --remove-orphans

# La première réponse peut attendre le chargement des embeddings :
# l'image prévoit 2 minutes de démarrage (HEALTHCHECK du Dockerfile).
status=starting
for _ in $(seq 1 60); do
  status=$(docker inspect -f '{{.State.Health.Status}}' "$($COMPOSE ps -q chatbot-api)" 2>/dev/null || echo missing)
  [ "$status" = healthy ] && break
  sleep 5
done

if [ "$status" != healthy ]; then
  echo "Le chatbot n'est pas healthy après 5 minutes (état : $status). Derniers journaux :"
  $COMPOSE logs chatbot-api --tail 60 --no-color
  exit 1
fi

# Images remplacées par le build : libère le disque.
docker image prune -f > /dev/null
echo "Déployé : $(git -c safe.directory='*' log --oneline -1)"
