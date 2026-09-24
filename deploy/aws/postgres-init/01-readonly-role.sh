#!/bin/sh
# Exécuté automatiquement par l'image postgres au PREMIER démarrage (volume
# vide) — voir docker-compose.aws.yml.
#
# Crée le rôle kiyanza_ro utilisé par le chatbot : lecture seule, et chaque
# requête limitée à 5 s (une requête générée par le LLM ne doit pas pouvoir
# bloquer la base). Les privilèges par défaut couvrent les tables créées
# PLUS TARD par kiyanza (ex: `campaigns`, recréée à chaque chargement de
# l'Excel par 02_load_excel_to_postgres.py).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE ROLE kiyanza_ro LOGIN PASSWORD '${DB_READONLY_PASSWORD}';
ALTER ROLE kiyanza_ro SET statement_timeout = '5s';
ALTER ROLE kiyanza_ro SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO kiyanza_ro;
GRANT USAGE ON SCHEMA public TO kiyanza_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO kiyanza_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public GRANT SELECT ON TABLES TO kiyanza_ro;
EOSQL
