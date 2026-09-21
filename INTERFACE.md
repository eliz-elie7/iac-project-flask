# Contrat d'interface — API Flask ↔ Couche d'orchestration (Ansible/Docker)

## Principe général

L'API Flask ne manipule jamais Docker ou Ansible directement. Elle appelle une couche
d'orchestration unique (`orchestrator.py`) qui expose les fonctions ci-dessous. Ce découplage
permet de développer et tester les deux côtés (application web / infrastructure) en parallèle.

---

## 1. Provisioning — créer une instance

```python
provision(
    user_id: int,
    distribution: str,      # ex: "ubuntu-22.04"
    duration_hours: int
) -> dict
```

### Déroulement interne (côté orchestration)
1. Génère un `instance_id` unique (UUID).
2. Génère une paire de clés SSH dédiée à cette instance (`instance_id.pub` / `instance_id.pem`).
3. Lance `docker compose up` (ou `docker run`) pour créer le conteneur correspondant à la
   distribution demandée.
4. Lance `ansible-playbook site.yml -i <ip_conteneur>, --extra-vars "pubkey=..."` pour injecter
   la clé publique et appliquer la configuration de base.
5. Retourne un résultat structuré à l'API.

### Retour attendu par l'API
```json
{
  "status": "success",
  "instance_id": "a1b2c3d4",
  "ssh_host": "127.0.0.1",
  "ssh_port": 2201,
  "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----..."
}
```

**Règle de sécurité** : `private_key` est affichée une seule fois à l'utilisateur côté interface
web, puis n'est jamais conservée en clair côté serveur (soit non stockée, soit stockée chiffrée
si une réémission est nécessaire).

---

## 2. Vérification de statut (support de la haute disponibilité)

```python
check_status(instance_id: str) -> dict
```

### Retour
```json
{ "instance_id": "a1b2c3d4", "status": "running" | "stopped" | "unreachable" }
```

L'API appelle cette fonction périodiquement (toutes les 30 à 60 secondes, via un scheduler) et
déclenche une réparation automatique si le statut est `unreachable`.

---

## 3. Réparation / redémarrage

```python
repair(instance_id: str) -> dict
```

Relance le conteneur concerné et ré-applique le playbook Ansible associé. Le playbook doit être
**idempotent** : une nouvelle exécution ne doit ni casser la configuration existante, ni changer
la clé SSH déjà en place chez l'utilisateur.

---

## 4. Fin de location / nettoyage

```python
teardown(instance_id: str) -> bool
```

Arrête et supprime le conteneur, et nettoie toutes les ressources associées (clés, entrées
réseau, etc.). Déclenchée automatiquement à l'expiration de la durée de location.

---

## 5. Convention technique commune

- Toutes ces fonctions vivent dans un module Python unique (`orchestrator.py`), importé
  directement par l'API Flask — pas d'appel shell externe si les deux parties du binôme
  travaillent en Python, pour faciliter le débogage.
- Chaque fonction lève une exception explicite en cas d'échec :
  - `ProvisioningError` — échec de création du conteneur ou du playbook
  - `TimeoutError` — l'instance ne répond pas dans le délai imparti
  - `TeardownError` — échec du nettoyage
- L'API attrape ces exceptions et traduit chacune en message clair pour l'utilisateur final
  (jamais de trace technique brute affichée côté interface web).

---

## Schéma des échanges

```
Utilisateur → Flask API → orchestrator.py → Docker / Ansible
                              ↑                    │
                              └── retour structuré ─┘
```

## Points à trancher (à documenter dans le rapport, section "Architecture")

- Mode d'affichage de la clé privée à l'utilisateur (texte affiché une fois / fichier .pem
  téléchargeable).
- Mécanisme exact de `check_status` : health-check natif Docker (`docker inspect`) ou script
  de vérification SSH actif.
