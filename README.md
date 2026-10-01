# Plateforme de location d'instances — Projet 3 (Outils déploiement plateformes)

Application web Flask permettant à un utilisateur de louer des instances (conteneurs)
éphémères avec accès SSH, hébergées dynamiquement sur un parc de Workers, avec haute
disponibilité en cas de panne d'un Worker.

Projet réalisé dans le cadre du cours *Outils déploiement plateformes* — INSA CVL, STI 4A-FISE,
2026/2027 (Dr. Nadia Fettah).

## Documentation complémentaire

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — décisions architecturales et leur justification
- [`INTERFACE.md`](./INTERFACE.md) — contrat de communication entre les composants

## Architecture en un coup d'œil

Utilisateur → Flask (Controller) → Resource Manager → Worker Agent (conteneur) → Docker/Ansible
↑ │
└──────── register / heartbeat ──────────┘


Trois Workers (`worker1`, `worker2`, `worker3`) sont simulés par des conteneurs Docker plutôt
que par des VM Vagrant (simplification validée par l'enseignante — voir `ARCHITECTURE.md`).

## Prérequis

- Docker et Docker Compose (v2, plugin intégré)
- Git

Aucune autre dépendance n'est nécessaire sur la machine hôte : Python, Ansible et les outils de
provisioning tournent exclusivement à l'intérieur des conteneurs.

## Installation et démarrage

```bash
git clone <url-du-repo>
cd iac-paas-projet
./setup.sh
```

Ce script :
1. Construit les images de base des instances louées (Ubuntu, Debian, avec SSH préinstallé)
2. Crée le fichier `.env` à partir de `.env.example` si absent
3. Démarre l'infrastructure complète (Flask, PostgreSQL, 3 Workers)
4. Applique les migrations de base de données
5. Peuple la table des distributions disponibles

L'application est ensuite accessible sur **http://localhost:5000**.

### Vérifier que tout tourne correctement

```bash
curl http://localhost:5000/workers
```
Doit renvoyer 3 Workers à l'état `AVAILABLE`.

## Utilisation

1. Créer un compte sur `/register`, se connecter sur `/login`
2. Depuis le dashboard, choisir une distribution et une durée, cliquer sur "Louer une instance"
3. La clé SSH privée s'affiche **une seule fois** — la copier immédiatement
4. Se connecter à l'instance :
```bash
   ssh -i votre_cle -p <port_affiché> root@localhost
```
5. Depuis le dashboard, l'instance peut être arrêtée manuellement avant son expiration

## Tester la haute disponibilité

### Panne d'une instance (réparation sur place)
```bash
docker exec instance-<id> pkill sshd
```
Sous 45 secondes, l'instance doit être détectée `unreachable` puis réparée automatiquement.

### Panne d'un Worker entier (migration)
```bash
docker compose stop worker2
```
Sous 60 secondes, `worker2` passe `OFFLINE` et ses instances actives sont recréées sur un autre
Worker disponible. Une bannière apparaît au prochain chargement du dashboard avec la nouvelle
clé SSH de l'instance migrée.

Pour remettre le Worker en service :
```bash
docker compose start worker2
```

## Variables d'environnement (`.env`)

| Variable | Rôle |
|---|---|
| `FLASK_APP` | Point d'entrée Flask (`app.app:app`) |
| `FLASK_SECRET_KEY` | Clé secrète Flask (sessions) — à changer en production |
| `DATABASE_URL` | Chaîne de connexion PostgreSQL |
| `INSTANCES_PUBLIC_HOST` | Adresse communiquée à l'utilisateur pour se connecter en SSH |

## Structure du projet

iac-paas-projet/
├── app/ # Controller Flask
│ ├── app.py # Point d'entrée (application factory)
│ ├── auth.py # Inscription / connexion / déconnexion
│ ├── dashboard.py # Dashboard, formulaire de location
│ ├── instances.py # API de gestion des instances (GET/stop)
│ ├── resource_manager.py # Sélection des Workers, délégation
│ ├── scheduler.py # Health-check, détection de panne, expiration
│ ├── validation.py # Validation des entrées utilisateur
│ ├── models.py # Modèles SQLAlchemy
│ └── migrations/ # Historique des migrations (Alembic)
├── worker/ # Worker Agent (identique sur chaque Worker)
│ └── agent.py
├── ansible/ # Playbook de configuration des instances louées
├── instances/ # Images de base + instances provisionnées à la volée
├── docker-compose.yml
└── setup.sh


## Stratégie de branches Git

Vu la taille de l'équipe (2 personnes), une stratégie simple est adoptée :
- `main` reste toujours dans un état fonctionnel et démontrable
- chaque nouvelle fonctionnalité ou correction se développe dans une branche courte
  (`feature/nom-de-la-fonctionnalité` ou `fix/nom-du-bug`), fusionnée dans `main` dès qu'elle
  est validée en local par les deux membres
- pas de branche de développement intermédiaire (`develop`) : inutile à cette échelle et cette
  durée de projet

## Limites connues du prototype

- Les Workers sont des conteneurs partageant le moteur Docker de l'hôte, pas des VM isolées
  (voir `ARCHITECTURE.md`)
- Pas de pipeline CI/CD, pas de scan de vulnérabilités automatisé (Trivy, gitleaks)
- Pas de suite de tests automatisés — validation réalisée manuellement au fil du développement
- Sélection de Worker simplifiée (dernier heartbeat reçu), sans répartition de charge par
  CPU/mémoire réelle

