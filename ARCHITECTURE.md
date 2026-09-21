# Architecture du projet — Décisions et justifications

Ce document recense les décisions architecturales du projet et leur justification. Il sert de
base directe à la section "Aperçu de l'architecture" du rapport final (un paragraphe par
décision).

Pour le détail du contrat de communication entre composants, voir `INTERFACE.md`.

---

## 1. Vue d'ensemble du flux

```
Utilisateur → Flask API → orchestrator.py → Docker / Ansible
                              ↑                    │
                              └── retour structuré ─┘
```

L'API Flask ne manipule jamais Docker ou Ansible directement : elle passe systématiquement par
`orchestrator.py`, qui expose une interface stable (voir `INTERFACE.md`). Ce découplage permet
de développer et tester la partie applicative et la partie infrastructure en parallèle, sans
dépendance bloquante entre les deux.

```text
                     UTILISATEUR (Navigateur Web)
                                  |
                                  v
                  APPLICATION WEB FLASK (Portail)
                                  |
        +-------------------------+-------------------------+
        |                                                   |
        v                                                   v
 Créer un compte                                          Login
        |                                                   |
        +-------------------------+-------------------------+
                                  |
                                  v
                    DASHBOARD (Tableau de bord)
                                  |
                        "Louer une instance"
                                  |
              +-------------------+-------------------+
              |                                       |
              v                                       v
    Choix de la Distribution                   Choix de la Durée
      (ex: Ubuntu, Debian)                       (ex: 2h, 24h)
              |                                       |
              +-------------------+-------------------+
                                  |
                                  v
                         API FLASK (Backend)
                                  |
        +-------------------------+-------------------------+
        |                                                   |
        v                                                   v
 BASE DE DONNÉES (PostgreSQL)                     ORCHESTRATION (IaC)
 Enregistrement de la location               1. Création du conteneur (Docker)
 et de l'état (InstanceState)                2. Provisionning & Sécu (Ansible)
        |                                                   |
        +-------------------------+-------------------------+
                                  |
                                  v
                    GÉNÉRATION DES ACCÈS SSH
                 (Affichage des logs sur le Dashboard)
                                  |
        +-------------------------+-------------------------+
        |                                                   |
        v                                                   v
 Accès direct pour le client                    Surveillance continue (HA)
 via Terminal (ssh user@ip -p)                  Health-checks & Relance si crash

---

## 2. Schéma de base de données

Trois entités composent le modèle de données.

### `User`
| Champ | Type | Note |
|---|---|---|
| `id` | int, PK | |
| `username` | string, unique | |
| `password_hash` | string | jamais le mot de passe en clair |
| `created_at` | datetime | |

### `Rental` (une location)
| Champ | Type | Note |
|---|---|---|
| `id` | int, PK | |
| `user_id` | FK → User | |
| `instance_id` | string, unique | UUID généré par l'orchestrateur |
| `distribution` | string | ex : "ubuntu-22.04" |
| `duration_hours` | int | |
| `started_at` | datetime | |
| `expires_at` | datetime | calculé à la création (`started_at + duration_hours`) |
| `status` | enum | `active`, `expired`, `terminated` |

### `InstanceState` (état technique, mis à jour par le health-check)
| Champ | Type | Note |
|---|---|---|
| `rental_id` | FK → Rental | relation 1-1 |
| `ssh_host` | string | |
| `ssh_port` | int | |
| `last_status` | enum | `running`, `stopped`, `unreachable` |
| `last_checked_at` | datetime | |
| `repair_attempts` | int | évite une boucle infinie de réparation |

**Justification du découpage `Rental` / `InstanceState`** : `Rental` porte la donnée métier
(ce que voit l'utilisateur), `InstanceState` porte la donnée technique mise à jour fréquemment
par le scheduler de haute disponibilité. Séparer les deux évite de mélanger les logiques et
isole les écritures fréquentes (health-check) des écritures rares (création de location).

**Règle de sécurité** : la clé privée SSH générée à la création d'une instance n'est jamais
stockée en base, même chiffrée. Elle n'existe que le temps d'être affichée une fois à
l'utilisateur.

---

## 3. Stratégie de haute disponibilité

### Déclencheur
Un scheduler léger côté Flask (`APScheduler`), suffisant pour un prototype — pas besoin d'une
file de tâches externe type Celery/Redis. Fréquence : toutes les 30 à 60 secondes.

### Déroulement de chaque cycle
1. Récupérer toutes les `Rental` avec `status = active`.
2. Pour chacune, appeler `orchestrator.check_status(instance_id)`.
3. Mettre à jour `InstanceState` avec le résultat.
4. Si le statut est `unreachable` : appeler `orchestrator.repair(instance_id)` et incrémenter
   `repair_attempts`.
5. Si `repair_attempts` dépasse un seuil (ex : 3) : marquer l'instance en échec et notifier
   l'utilisateur plutôt que de retenter indéfiniment.

### Méthode de détection du statut
Privilégier une tentative de connexion SSH active (ex : `ssh -o ConnectTimeout=3` ou une
bibliothèque comme `paramiko`) plutôt qu'un simple `docker inspect`, qui confirme qu'un
conteneur tourne mais pas qu'il est réellement joignable.

### Gestion de l'expiration
Le même cycle de scheduler vérifie les `Rental` dont `expires_at` est dépassé et déclenche
`orchestrator.teardown(instance_id)`.

---

## 4. Points encore à trancher

- Mode d'affichage de la clé privée à l'utilisateur (texte affiché une fois dans le dashboard,
  ou fichier `.pem` téléchargeable).
- ORM (SQLAlchemy) ou SQL brut pour la couche base de données — recommandé : ORM, pour la
  rapidité d'évolution du schéma pendant le développement.
