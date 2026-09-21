#!/usr/bin/env bash
set -e

echo "==> Vérification des prérequis (docker, ansible, ssh-keygen)..."
command -v docker >/dev/null 2>&1 || { echo "Docker n'est pas installé. Abandon."; exit 1; }
command -v ansible-playbook >/dev/null 2>&1 || { echo "Ansible n'est pas installé. Abandon."; exit 1; }
command -v ssh-keygen >/dev/null 2>&1 || { echo "ssh-keygen n'est pas disponible. Abandon."; exit 1; }

echo "==> Construction des images de base (avec SSH préinstallé)..."
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

echo "==> Démarrage de l'infrastructure centrale (Flask + PostgreSQL)..."
docker compose up -d --build

echo "==> Application des migrations de base de données..."
docker compose exec web flask db upgrade

echo "==> Terminé. L'application est disponible sur http://localhost:5000"