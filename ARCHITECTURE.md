# Architecture du projet — Décisions et justifications

Ce document recense les décisions architecturales du projet et leur justification. Il sert de
base directe à la section "Aperçu de l'architecture" du rapport final (un paragraphe par
décision).

Pour le détail du contrat de communication entre composants, voir `INTERFACE.md`.

---

## 1. Vue d'ensemble du flux

```
Utilisateur → Flask (Controller) → Resource Manager → Worker Agent (conteneur) → Docker/Ansible
                    ↑                                        │
                    └──────── register / heartbeat ──────────┘
```

Le Controller ne manipule jamais Docker ou Ansible directement : il délègue au Resource
Manager, qui sélectionne un Worker disponible et communique avec son Worker Agent via une API
interne stable (voir `INTERFACE.md`). Ce découplage permet de développer et de tester la partie
applicative (Flask, BDD) et la partie infrastructure (provisioning, Ansible) séparément.

---

## 2. Infrastructure multi-Worker : trois VM Vagrant provisionnées par Ansible

Les trois Workers (`worker1`, `worker2`, `worker3`) sont de véritables machines virtuelles,
déclarées dans un `Vagrantfile` à la racine du projet (box Ubuntu 22.04, 1 vCPU, 1 Go de RAM,
provider libvirt/KVM ; VirtualBox est également supporté par le même fichier). Chaque VM possède
son propre noyau, son propre moteur Docker et une adresse sur un réseau privé dédié
(192.168.56.11 à .13), ce qui garantit une isolation réelle entre Workers.

**Provisioning par Ansible (push model)** : après `vagrant up`, le playbook maître `site.yml`
enchaîne trois playbooks idempotents :
- `docker.yml` : installation de Docker Engine et du plugin Compose ;
- `worker.yml` : déploiement du Worker Agent (code, environnement virtuel Python, collections
  Ansible, template docker-compose, construction des images de base avec SSH préinstallé,
  fichier d'environnement et unité systemd) ;
- `deploy.yml` : démarrage du service `worker-agent` et attente de sa disponibilité.

L'agent tourne en service systemd (redémarrage automatique en cas de crash) et s'enregistre
lui-même auprès du Controller. Les images de base des instances louées sont construites sur
chaque Worker, puisque chaque VM a son propre moteur Docker.

**Le Controller** (Flask, Resource Manager, scheduler) et sa base PostgreSQL tournent via
Docker Compose sur la machine hôte. Le service `web` utilise le réseau de l'hôte
(`network_mode: host`) pour joindre directement les VM : le trafic d'un conteneur Docker vers
un réseau libvirt est filtré par défaut par le pare-feu de l'hôte, alors que l'hôte lui-même
atteint les VM sans difficulté. Ce choix est une simplification assumée : le Controller n'est
pas lui-même une VM Vagrant.

**Justification** : le Controller concentre la logique applicative en cours de
développement (rechargement du code monté en volume), et le virtualiser aurait ajouté une
couche de déploiement sans changer le comportement du système. Le contrat d'interface avec les
Workers (voir `INTERFACE.md`) est indépendant du lieu d'exécution du Controller : le
déplacer dans une VM reste possible sans modifier les Workers.

**Réseau** : un réseau libvirt dédié (`vagrant-workers`, 192.168.56.0/24) relie l'hôte
(192.168.56.1) et les trois VM. Les VM joignent le Controller sur 192.168.56.1:5000, le
Controller joint les agents sur leur IP, port 6000.

---

## 3. Schéma de base de données

Cinq entités composent le modèle de données.

### `User`
| Champ | Type | Note |
|---|---|---|
| `id` | int, PK | |
| `username` | string, unique | |
| `password_hash` | string | jamais le mot de passe en clair |
| `created_at` | datetime | |

### `Distribution`
| Champ | Type | Note |
|---|---|---|
| `id` | int, PK | |
| `name` | string, unique | ex : "ubuntu-22.04" |
| `docker_image` | string | image construite localement avec SSH préinstallé |
| `version` | string | |
| `status` | enum | `active`, `disabled` |

**Justification** : les distributions disponibles sont désormais des données, pas du code en
dur. On peut en ajouter ou en désactiver une sans toucher à l'application.

### `Worker`
| Champ | Type | Note |
|---|---|---|
| `id` | int, PK | |
| `hostname` | string, unique | ex : "worker1" |
| `ip` | string | IP privée de la VM : sert à la fois au Controller pour joindre l'agent et à l'utilisateur pour la connexion SSH |
| `status` | enum | `AVAILABLE`, `BUSY`, `OFFLINE` |
| `cpu` | string | rapporté par le Worker Agent au heartbeat |
| `memory` | string | idem |
| `last_heartbeat` | datetime | mis à jour à chaque heartbeat reçu |

### `Instance`
| Champ | Type | Note |
|---|---|---|
| `id` | int, PK | |
| `container_id` | string | identifiant court généré par le Worker Agent |
| `worker_id` | FK → Worker | Worker qui héberge cette instance |
| `distribution_id` | FK → Distribution | |
| `ssh_port` | int | |
| `status` | enum | `running`, `stopped`, `unreachable` |
| `created_at` | datetime | |

### `Rental` (une location)
| Champ | Type | Note |
|---|---|---|
| `id` | int, PK | |
| `user_id` | FK → User | |
| `instance_id` | FK → Instance, unique | relation 1-1 |
| `start_time` | datetime | |
| `end_time` | datetime | calculé à la création (`start_time + duration_hours`) |
| `status` | enum | `active`, `expired`, `terminated` |

**Justification du découpage `Instance` / `Rental`** : `Instance` porte la donnée technique
(quel conteneur, sur quel Worker, quel port), `Rental` porte la donnée métier (qui loue, pour
combien de temps). Une instance peut ainsi changer de Worker (migration suite à une panne) sans
toucher à l'historique de la location elle-même.

**Règle de sécurité** : la clé privée SSH générée à la création (ou à la migration) d'une
instance n'est jamais stockée en base, même chiffrée. Elle n'existe que le temps d'être
affichée une fois à l'utilisateur.

---

## 4. Resource Manager : sélection et affectation des Workers

Le Resource Manager (module `app/resource_manager.py`, côté Controller) est responsable de :
- recevoir les enregistrements et heartbeats des Worker Agents,
- sélectionner un Worker `AVAILABLE` lors d'une nouvelle location (stratégie simple : le
  Worker dont le heartbeat est le plus récent, sans équilibrage fin par charge CPU/mémoire —
  volontairement simplifié pour un prototype),
- déléguer le provisioning, la vérification, la réparation et le nettoyage au Worker Agent
  concerné via l'API interne définie dans `INTERFACE.md`.

---

## 5. Stratégie de haute disponibilité (deux niveaux)

Le document de cadrage distingue deux formes de résilience, que nous traitons séparément.

### Niveau instance : une instance ne répond plus, mais son Worker est sain
- Détection : tentative de connexion SSH active (pas seulement `docker inspect`, qui confirme
  qu'un conteneur tourne mais pas qu'il est réellement joignable).
- Fréquence : toutes les 45 secondes.
- Action : réparation sur place (`docker compose up -d` + ré-application idempotente du
  playbook Ansible), sans changer la clé SSH existante.

### Niveau Worker : un Worker entier tombe en panne
- Détection : absence de heartbeat pendant plus de 60 secondes (soit 3 cycles de heartbeat de
  20 secondes, pour tolérer un aléa réseau ponctuel).
- Fréquence de vérification : toutes les 30 secondes.
- Action : le Worker est marqué `OFFLINE`, et chaque instance active qu'il hébergeait est
  **recréée** sur un autre Worker disponible (et non déplacée, ce qui serait impossible
  puisque le Worker en panne ne répond plus).
- Conséquence assumée : l'instance recréée obtient une nouvelle clé SSH. L'utilisateur est
  informé via une notification affichée une seule fois à son prochain accès au dashboard,
  jamais persistée en base (cohérent avec la règle de non-stockage des clés privées).

### Gestion de l'expiration
Un troisième cycle de scheduler (toutes les 60 secondes) vérifie les `Rental` dont `end_time`
est dépassé et déclenche le teardown de l'instance correspondante sur son Worker actuel.

---

## 6. Points encore à trancher

- Mode d'affichage de la clé privée à l'utilisateur (texte affiché une fois dans le dashboard,
  ou fichier `.pem` téléchargeable).
- Stratégie de sélection de Worker plus fine (répartition par charge CPU/mémoire réelle),
  actuellement simplifiée au profit du heartbeat le plus récent.