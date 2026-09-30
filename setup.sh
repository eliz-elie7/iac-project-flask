#!/usr/bin/env bash
set -e

echo "==> Vérification des prérequis (docker)..."
command -v docker >/dev/null 2>&1 || { echo "Docker n'est pas installé. Abandon."; exit 1; }

echo "==> Construction des images de base pour les instances louées (avec SSH préinstallé)..."
docker build -t iac-project/ubuntu-22.04-ssh instances/images/ubuntu-22.04
docker build -t iac-project/debian-12-ssh instances/images/debian-12

echo "==> Préparation du fichier .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Fichier .env créé à partir de .env.example — pensez à vérifier/modifier les valeurs."
else
    echo ".env existe déjà, on ne le touche pas."
fi

echo "==> Création des dossiers nécessaires (clés SSH, instances)..."
mkdir -p instances/keys

echo "==> Démarrage de toute l'infrastructure (Flask, PostgreSQL, Workers)..."
docker compose up -d --build

echo "==> Application des migrations de base de données..."
if [ ! -d "app/migrations" ]; then
    docker compose run --rm web flask db init
    docker compose run --rm web flask db migrate -m "initial schema"
fi
docker compose run --rm web flask db upgrade

echo "==> Peuplement des distributions disponibles..."
docker compose exec -T web flask shell <<'PY'
from app.seed import seed_distributions
seed_distributions()
PY

echo "==> Terminé. L'application est disponible sur http://localhost:5000"
echo "    Les Workers devraient apparaître via GET http://localhost:5000/workers d'ici quelques secondes."