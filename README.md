# Plateforme de location d'instances — Projet 3 (Outils déploiement plateformes)

Application web Flask permettant de louer des instances (conteneurs) éphémères avec accès SSH,
hébergées dynamiquement sur un parc de 3 Workers (machines virtuelles Vagrant), avec haute
disponibilité en cas de panne d'une instance ou d'un Worker.

Projet INSA CVL — STI 4A-FISE, 2026/2027 (Dr. Nadia Fettah).
Auteurs : Eliezer Djihinto, Abdoulaye Diallo, Karim Hassini, Rayane Essalhi.

## Documentation complémentaire

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — décisions architecturales et justifications
- [`INTERFACE.md`](./INTERFACE.md) — contrat de communication Controller ↔ Worker Agent

## Architecture en un coup d'œil

```
Utilisateur → Flask (Controller) → Resource Manager → Worker Agent (VM Vagrant) → Docker/Ansible
                    ↑                                        │
                    └──────── register / heartbeat ──────────┘
```

- **Controller** : Flask, Resource Manager, scheduler et PostgreSQL, via Docker Compose sur l'hôte.
- **Workers** : 3 VM Vagrant (192.168.56.11 à .13), provisionnées par Ansible (`site.yml`).
  Chaque VM a son propre moteur Docker et un Worker Agent (service systemd).

## Prérequis

- Docker et Docker Compose v2
- Vagrant et un provider : **libvirt** (`vagrant-libvirt`, recommandé sous Linux) ou VirtualBox
- Ansible
- Git

## Installation et démarrage

```bash
git clone <url-du-repo>
cd iac-paas-projet
./setup.sh                                   # provider libvirt par défaut
VAGRANT_PROVIDER=virtualbox ./setup.sh       # pour VirtualBox
```

Le script démarre les VM, les provisionne avec Ansible, lance le Controller, applique les
migrations et peuple les distributions. Application : **http://localhost:5000**.

Étapes manuelles équivalentes :

```bash
vagrant up --provider=libvirt --no-parallel
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/site.yml
docker compose up -d --build
curl http://localhost:5000/workers          # 3 Workers AVAILABLE
```

## Réseau (Linux avec Docker + libvirt)

Docker met la politique `FORWARD` du pare-feu à `DROP`, ce qui coupe l'accès Internet des VM.
Autoriser les ponts libvirt :

```bash
sudo iptables -I DOCKER-USER -i virbr+ -j ACCEPT
sudo iptables -I DOCKER-USER -o virbr+ -j ACCEPT
sudo firewall-cmd --zone=libvirt --add-port=5000/tcp   # les VM joignent le Controller
```

Si les VM ne répondent plus après un changement de VM : `sudo ip neigh flush dev virbr-workers`.
La clé SSH utilisée par Ansible est celle générée par Vagrant ; avec VirtualBox, remplacer
`libvirt` par `virtualbox` dans les chemins de `ansible/inventory/hosts.ini`.

## Utilisation

1. Créer un compte (`/register`), se connecter (`/login`).
2. Depuis le dashboard : choisir une distribution et une durée, cliquer sur « Louer ».
3. La clé SSH privée s'affiche **une seule fois** : la copier immédiatement.
4. `ssh -i votre_cle -p <port> root@<IP du Worker>`
5. L'instance peut être arrêtée depuis le dashboard avant son expiration.

## Tester la haute disponibilité

- **Instance** : `vagrant ssh worker1 -c "sudo docker exec instance-<id> pkill sshd"` → réparée en ~45 s.
- **Worker** : `vagrant halt worker2` → `OFFLINE` après ~60 s, ses instances sont recréées sur un
  autre Worker, une bannière affiche la nouvelle clé SSH. Remise en ligne : `vagrant up worker2 --provider=libvirt`.
- **Idempotence Ansible** : relancer deux fois `site.yml`.

## Structure du projet

```
iac-paas-projet/
├── Vagrantfile              # 3 Workers (worker1..3)
├── ansible/
│   ├── inventory/hosts.ini  # inventaire des Workers
│   └── playbooks/           # site.yml, docker.yml, worker.yml, deploy.yml, configure_instance.yml
├── app/                     # Controller Flask (auth, dashboard, resource_manager, scheduler, models)
├── worker/                  # Worker Agent (agent.py), déployé sur chaque VM par Ansible
├── instances/               # Dockerfile des images de base + template docker-compose
├── docker-compose.yml       # Controller (web) + PostgreSQL (db)
└── setup.sh
```

## Stratégie de branches Git

`main` reste toujours démontrable ; chaque fonctionnalité ou correction se développe dans une
branche courte (`feature/...`, `fix/...`) fusionnée dès validation par deux membres.

## Limites connues

- Le Controller tourne via Docker Compose sur l'hôte, il n'est pas lui-même une VM Vagrant.
- Pas de pipeline CI/CD, pas de scan automatisé (Trivy, gitleaks), pas de tests automatisés.
- Les Workers exécutent l'agent en root ; sélection de Worker simplifiée (dernier heartbeat).