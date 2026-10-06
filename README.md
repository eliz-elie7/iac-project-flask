# 🖥️ Plateforme de location d'instances

> Plateforme web de location d'instances éphémères avec accès SSH, déployées dynamiquement sur un parc de Workers Docker et supervisées par un système de **haute disponibilité**.

**Projet 3 — Outils de déploiement de plateformes**
**INSA Centre Val de Loire — STI 4A-FISE — 2026/2027**
**Enseignante : Dr. Nadia Fettah**

---

## 📌 Présentation

Cette application permet à un utilisateur de :

* créer un compte et se connecter ;
* choisir une distribution Linux disponible ;
* louer une instance pour une durée déterminée ;
* accéder à l'instance via **SSH** ;
* arrêter manuellement une instance avant son expiration ;
* récupérer les informations de connexion depuis le dashboard ;
* bénéficier d'une migration automatique en cas de panne d'un Worker.

Les instances sont déployées sous forme de **conteneurs Docker éphémères** et réparties dynamiquement sur plusieurs Workers.

Le projet met principalement en œuvre des concepts d'**Infrastructure as Code (IaC)**, de déploiement automatisé, d'orchestration de conteneurs et de haute disponibilité.

---

## 🏗️ Architecture

```text
                         ┌─────────────────────┐
                         │       Utilisateur   │
                         │    Web + SSH        │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Flask Web App    │
                         │     Controller      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Resource Manager  │
                         │  Sélection Worker   │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │ Worker 1 │   │ Worker 2 │   │ Worker 3 │
              │  Agent   │   │  Agent   │   │  Agent   │
              └────┬─────┘   └────┬─────┘   └────┬─────┘
                   │              │              │
                   └──────────────┼──────────────┘
                                  ▼
                         ┌─────────────────┐
                         │ Docker / Ansible│
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │ Instance louée  │
                         │ Ubuntu / Debian │
                         │       + SSH     │
                         └─────────────────┘
```

### Composants principaux

| Composant            | Rôle                                                           |
| -------------------- | -------------------------------------------------------------- |
| **Flask**            | Interface web, authentification et gestion des locations       |
| **Resource Manager** | Sélection et attribution des Workers                           |
| **Worker Agent**     | Création, supervision et suppression des instances             |
| **PostgreSQL**       | Stockage des utilisateurs, Workers, instances et locations     |
| **Docker**           | Isolation et exécution des instances                           |
| **Ansible**          | Provisionnement et configuration des instances                 |
| **Scheduler**        | Health-check, détection des pannes et expiration des locations |

Les trois Workers (`worker1`, `worker2`, `worker3`) sont simulés par des conteneurs Docker plutôt que par des machines virtuelles Vagrant. Cette simplification a été validée dans le cadre du projet.

Pour plus de détails :

* [`ARCHITECTURE.md`](./ARCHITECTURE.md) — décisions architecturales et justifications
* [`INTERFACE.md`](./INTERFACE.md) — contrat de communication entre les composants

---

## ⚙️ Fonctionnalités

### 👤 Gestion utilisateur

* Inscription
* Connexion / déconnexion
* Gestion de session avec Flask-Login

### 🖥️ Gestion des instances

* Sélection d'une distribution Linux
* Choix de la durée de location
* Création automatique de l'instance
* Génération d'une clé SSH
* Accès SSH à l'instance
* Arrêt manuel d'une instance
* Expiration automatique des locations

### 🔄 Haute disponibilité

* Heartbeat régulier des Workers
* Détection automatique d'un Worker indisponible
* Migration des instances actives vers un Worker disponible
* Réparation automatique d'une instance dont le service SSH est défaillant

### 🛠️ Provisionnement

Les instances sont automatiquement :

1. créées sur un Worker disponible ;
2. configurées avec Ansible ;
3. équipées d'un serveur SSH ;
4. associées à une clé SSH générée pour l'utilisateur ;
5. rendues accessibles depuis l'application.

---

## 🧰 Technologies utilisées

### Backend

* **Python 3.12**
* **Flask**
* **SQLAlchemy**
* **Flask-Migrate / Alembic**
* **PostgreSQL**

### Infrastructure

* **Docker**
* **Docker Compose**
* **Ansible**
* **OpenSSH**

### Frontend

* **HTML5**
* **CSS3**
* **Jinja2**
* JavaScript vanilla pour les fonctionnalités d'interface

---

## 📋 Prérequis

La machine hôte doit disposer de :

* [Docker](https://docs.docker.com/get-docker/)
* Docker Compose v2 (plugin Docker intégré)
* Git

Aucune installation supplémentaire de Python, Ansible ou des outils de provisioning n'est nécessaire sur la machine hôte : ces composants sont exécutés dans les conteneurs.

---

## 🚀 Installation

### 1. Cloner le projet

```bash
git clone <url-du-repo>
cd iac-project-flask
```

### 2. Lancer l'installation

```bash
bash setup.sh
```

Le script effectue automatiquement les opérations suivantes :

1. vérification de Docker ;
2. construction des images de base Ubuntu et Debian ;
3. installation de SSH dans les images ;
4. création du fichier `.env` s'il n'existe pas ;
5. création des dossiers nécessaires ;
6. construction des images Flask et Workers ;
7. démarrage de PostgreSQL, Flask et des trois Workers ;
8. application des migrations de base de données ;
9. initialisation des distributions Linux disponibles.

Une fois l'installation terminée, l'application est disponible à :

**http://localhost:5000**

---

## 🔎 Vérifier le fonctionnement

Vérifier que tous les conteneurs sont démarrés :

```bash
docker compose ps
```

Vous devez retrouver :

```text
db
web
worker1
worker2
worker3
```

Vérifier ensuite l'état des Workers :

```bash
curl http://localhost:5000/workers
```

Les trois Workers doivent apparaître avec l'état :

```text
AVAILABLE
```

Vous pouvez également accéder directement à :

```text
http://localhost:5000/workers
```

---

## 🖥️ Utilisation

### 1. Créer un compte

Accéder à :

```text
http://localhost:5000/register
```

Puis se connecter :

```text
http://localhost:5000/login
```

### 2. Louer une instance

Depuis le dashboard :

1. choisir une distribution ;
2. sélectionner une durée ;
3. cliquer sur **Louer une instance** ;
4. attendre la création et le provisionnement de l'instance.

### 3. Récupérer la clé SSH

Lors de la création, une clé privée SSH est générée.

> ⚠️ **La clé privée est affichée une seule fois.**

Elle doit être copiée ou téléchargée immédiatement.

### 4. Se connecter en SSH

Une fois l'instance créée, l'application affiche le port SSH à utiliser.

```bash
chmod 600 votre_cle.pem

ssh -i votre_cle.pem -p <port> root@localhost
```

### 5. Arrêter une instance

Une instance active peut être arrêtée depuis le dashboard avant la fin de sa durée de location.

---

# 🔄 Tests de haute disponibilité

Le projet inclut deux scénarios principaux permettant de tester la résilience de la plateforme.

## 1. Panne du serveur SSH d'une instance

Simuler une panne du service SSH :

```bash
docker exec instance-<id> pkill sshd
```

Le système doit :

1. détecter que l'instance est inaccessible ;
2. identifier la panne ;
3. lancer automatiquement une procédure de réparation ;
4. restaurer l'accès SSH.

La réparation est attendue sous **45 secondes**.

---

## 2. Panne complète d'un Worker

Arrêter un Worker :

```bash
docker compose stop worker2
```

Le système doit détecter que `worker2` ne répond plus.

Son état passe alors à :

```text
OFFLINE
```

Les instances actives hébergées sur ce Worker sont automatiquement recréées sur un autre Worker disponible.

Une notification apparaît ensuite sur le dashboard avec les nouvelles informations de connexion.

La migration est attendue sous **60 secondes**.

### Remettre le Worker en service

```bash
docker compose start worker2
```

---

## 🔐 Variables d'environnement

Le projet utilise un fichier `.env` pour configurer l'application.

| Variable                | Description                                                  |
| ----------------------- | ------------------------------------------------------------ |
| `FLASK_APP`             | Point d'entrée de l'application Flask                        |
| `FLASK_SECRET_KEY`      | Clé secrète utilisée pour les sessions Flask                 |
| `DATABASE_URL`          | URL de connexion PostgreSQL                                  |
| `INSTANCES_PUBLIC_HOST` | Adresse communiquée aux utilisateurs pour les connexions SSH |

> ⚠️ Les secrets et variables sensibles ne doivent jamais être commités dans Git.

---

## 📁 Structure du projet

```text
iac-project-flask/
│
├── app/
│   ├── app.py                  # Application Flask
│   ├── auth.py                 # Inscription / connexion / déconnexion
│   ├── dashboard.py            # Dashboard et location d'instances
│   ├── instances.py            # Gestion des instances
│   ├── resource_manager.py     # Sélection et gestion des Workers
│   ├── scheduler.py            # Health-check et supervision
│   ├── validation.py           # Validation des entrées utilisateur
│   ├── models.py               # Modèles SQLAlchemy
│   │
│   ├── templates/              # Templates HTML / Jinja2
│   ├── static/                 # CSS et ressources statiques
│   │
│   └── migrations/             # Migrations Alembic
│
├── worker/
│   └── agent.py                # Agent exécuté sur chaque Worker
│
├── ansible/
│   └── ...                     # Provisionnement des instances
│
├── instances/
│   └── ...                     # Images et instances provisionnées
│
├── docker-compose.yml          # Orchestration des services
├── setup.sh                    # Installation et démarrage
├── ARCHITECTURE.md             # Documentation de l'architecture
└── INTERFACE.md                # Contrat entre les composants
```

---

## 🎓 Contexte académique

Projet réalisé dans le cadre du cours :

**Outils de déploiement de plateformes**
INSA Centre Val de Loire — STI 4A-FISE
Année universitaire **2026/2027**

L'objectif du projet est de mettre en pratique les concepts de :

* Infrastructure as Code ;
* conteneurisation ;
* automatisation du déploiement ;
* orchestration ;
* supervision ;
* tolérance aux pannes ;
* haute disponibilité ;
* gestion des ressources.

---

## 👥 Équipe

Projet réalisé en binôme dans le cadre du Projet 3.

* **Karim**
* **Elie**
* **Abdoulaye**
* **Rayane**

---

## 📄 Documentation

Pour approfondir le fonctionnement du projet :

* [`ARCHITECTURE.md`](./ARCHITECTURE.md)
* [`INTERFACE.md`](./INTERFACE.md)

---

**Projet 3 — Outils de déploiement de plateformes — INSA CVL — 2026/2027**
