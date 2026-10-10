#!/usr/bin/env bash
# Démarre toute la plateforme : 3 Workers (VM Vagrant) + Controller (Flask + PostgreSQL).
# À lancer depuis la racine du projet.
set -e

PROVIDER="${VAGRANT_PROVIDER:-libvirt}"   # ou : VAGRANT_PROVIDER=virtualbox ./setup.sh

echo "==> Vérification des prérequis (docker, vagrant, ansible)..."
for cmd in docker vagrant ansible-playbook; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "$cmd n'est pas installé. Abandon."; exit 1; }
done

echo "==> Préparation du fichier .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Fichier .env créé à partir de .env.example — pensez à vérifier/modifier les valeurs."
else
    echo ".env existe déjà, on ne le touche pas."
fi

echo "==> Démarrage des 3 Workers (VM Vagrant, provider : $PROVIDER)..."
vagrant up --provider="$PROVIDER" --no-parallel

echo "==> Provisioning des Workers avec Ansible (Docker, Worker Agent, images de base)..."
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/site.yml

echo "==> Démarrage du Controller (Flask + PostgreSQL)..."
docker compose up -d --build db
sleep 8

echo "==> Migrations de base de données..."
if [ ! -d "app/migrations" ]; then
    docker compose run --rm web flask db init
    docker compose run --rm web flask db migrate -m "schema initial"
fi
docker compose run --rm web flask db upgrade

echo "==> Démarrage de l'application..."
docker compose up -d --build web

echo "==> Peuplement des distributions disponibles..."
sleep 5
docker compose exec web python -c "
from app.app import app
from app.seed import seed_distributions
with app.app_context():
    seed_distributions()
"

echo "==> Terminé. Application : http://localhost:5000"
echo "    Les 3 Workers apparaissent sur http://localhost:5000/workers d'ici ~20 secondes."
echo "    Sous Fedora/Linux avec Docker + libvirt, voir la section « Réseau » du README si les VM n'ont pas Internet."