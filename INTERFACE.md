# Contrat d'interface — Controller ↔ Resource Manager ↔ Worker Agent

## Principe général

Le Controller (Flask) ne manipule jamais Docker ou Ansible directement. Il délègue toute
opération sur une instance au **Resource Manager** (module interne du Controller), qui
sélectionne un Worker disponible et communique avec son **Worker Agent** via une petite API
HTTP interne, jamais exposée à l'extérieur du réseau Docker Compose.

```
Utilisateur → Flask (Controller) → Resource Manager → Worker Agent (conteneur) → Docker/Ansible
                    ↑                                        │
                    └──────── register / heartbeat ──────────┘
```

Chaque Worker est un conteneur Docker autonome faisant tourner un agent Python/Flask. Trois
Workers sont déployés (`worker1`, `worker2`, `worker3`), chacun avec son propre accès au
moteur Docker de l'hôte.

**Simplification assumée et validée par l'enseignante** : les Workers sont des conteneurs
partageant le moteur Docker de la machine hôte, et non des VM Vagrant isolées. Voir
`ARCHITECTURE.md` pour la justification complète.

---

## 1. Enregistrement d'un Worker (Worker Agent → Controller)

```
POST /workers/register
Body : { "hostname": str, "ip": str, "cpu": str, "memory": str }
Retour : { "worker_id": int }
```

Appelé automatiquement au démarrage de chaque Worker Agent. Si le `hostname` est déjà connu
(redémarrage d'un agent existant), le Worker est simplement remis à `AVAILABLE` plutôt que
dupliqué.

## 2. Heartbeat périodique (Worker Agent → Controller)

```
POST /workers/heartbeat
Body : { "worker_id": int, "status": str, "cpu": str, "memory": str }
Retour : { "status": "ok" }
```

Envoyé toutes les 20 secondes. Si le Controller ne reçoit aucun heartbeat d'un Worker pendant
plus de 60 secondes, celui-ci est déclaré `OFFLINE` par le scheduler et ses instances sont
migrées (voir section 6).

## 3. Provisioning d'une instance (Resource Manager → Worker Agent choisi)

```
POST http://<worker_hostname>:6000/internal/provision
Body : { "instance_id": str, "docker_image": str }
```

### Déroulement interne côté Worker Agent
1. Génère un fichier `docker-compose.yml` dédié à partir du template, avec un port SSH libre
   dans la plage 22000-22999.
2. Lance `docker compose up -d`.
3. Génère une paire de clés SSH dédiée à cette instance.
4. Applique le playbook Ansible (`configure_instance.yml`) via connexion `docker exec`
   (module `community.docker.docker`), qui injecte la clé publique. Idempotent.

### Retour attendu
```json
{
  "instance_id": "a1b2c3d4",
  "container_id": "instance-a1b2c3d4",
  "ssh_host": "<adresse publique du Worker>",
  "ssh_port": 22750,
  "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----..."
}
```

**Règle de sécurité inchangée** : `private_key` est affichée une seule fois côté interface
web, jamais stockée en base, ni côté Controller ni côté Worker.

## 4. Vérification de statut

```
GET http://<worker_hostname>:6000/internal/status/<instance_id>
Retour : { "status": "running" | "stopped" | "unreachable" }
```

Le Worker Agent vérifie que le conteneur tourne (`docker inspect`) puis tente une connexion
TCP vers son propre port SSH exposé sur l'hôte (`host.docker.internal`), sans authentification,
pour confirmer que `sshd` répond réellement (pas seulement que le conteneur est démarré).

## 5. Réparation (même Worker)

```
POST http://<worker_hostname>:6000/internal/repair/<instance_id>
Retour : { "status": "repaired" }
```

Relance le conteneur (`docker compose up -d`, idempotent) et ré-applique le playbook Ansible
sans changer la clé SSH existante. Utilisé quand l'instance est `unreachable` mais que son
Worker est toujours sain.

## 6. Migration vers un nouveau Worker (panne du Worker hébergeant l'instance)

Quand un Worker est déclaré `OFFLINE` (heartbeat expiré), le Resource Manager provisionne une
**nouvelle** instance sur un autre Worker disponible, pour chaque instance active hébergée sur
le Worker en panne — il ne s'agit pas d'un déplacement du conteneur existant (impossible, le
Worker ne répond plus), mais d'une recréation.

Conséquence assumée : l'instance recréée obtient une **nouvelle clé SSH**. La clé précédente
est perdue. L'utilisateur est informé via une notification éphémère affichée une seule fois au
prochain chargement du dashboard (jamais persistée en base).

## 7. Fin de location / nettoyage

```
POST http://<worker_hostname>:6000/internal/teardown/<instance_id>
Retour : { "status": "removed" }
```

Arrête et supprime le conteneur, nettoie les clés SSH et le dossier de l'instance.

---

## Convention technique commune

- Toutes les fonctions du Resource Manager vivent dans `app/resource_manager.py`, appelées par
  `app/dashboard.py` et `app/scheduler.py`.
- Toute la logique Docker/Ansible vit dans `worker/agent.py`, jamais importée directement par
  le Controller.
- Les échecs HTTP entre Resource Manager et Worker Agent sont traduits en exceptions Python
  explicites côté Controller :
  - `NoWorkerAvailableError` — aucun Worker `AVAILABLE` au moment de la demande
  - `ProvisioningError` — échec renvoyé par l'agent (image introuvable, échec Ansible, etc.)
- Le port interne des agents (6000) n'est jamais exposé sur l'hôte — seul le réseau Docker
  Compose interne y donne accès.

## Points tranchés

- Stockage de la clé privée : affichée une fois dans le dashboard au moment de la création (ou
  d'une migration), jamais conservée.
- Détection de statut : tentative de connexion SSH active plutôt qu'un simple `docker inspect`,
  pour confirmer une joignabilité réelle et pas seulement l'état du conteneur.
- Sélection du Worker : le premier `AVAILABLE` par ordre de heartbeat le plus récent — pas de
  stratégie de répartition de charge plus fine (CPU/mémoire), volontairement simplifié pour un
  prototype.