import glob
import json
import os
import random
import re
import shutil
import socket
import subprocess
import tempfile
import uuid

from jinja2 import Template

INSTANCES_DIR = "instances"
TEMPLATE_PATH = "instances/templates/docker-compose.template.yml"
ANSIBLE_PLAYBOOK = "ansible/playbooks/configure_instance.yml"
KEYS_DIR = "instances/keys"

CONTAINER_PREFIX = "instance-"
PORT_RANGE = (22000, 22999)
PUBLIC_HOST = os.environ.get("INSTANCES_PUBLIC_HOST", "localhost")  # adresse donnée à l'utilisateur
INTERNAL_HOST = "host.docker.internal"  # l'hôte, vu depuis le conteneur web

DISTRIBUTION_IMAGES = {
    "ubuntu-22.04": "iac-project/ubuntu-22.04-ssh",
    "debian-12": "iac-project/debian-12-ssh",
}


class ProvisioningError(Exception):
    pass

class TimeoutError(Exception):
    pass

class TeardownError(Exception):
    pass


# ---------- Utilitaires ----------

def _run(cmd: list, timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Délai dépassé : {' '.join(cmd[:3])}...")


def _compose_path(instance_id: str) -> str:
    return os.path.join(INSTANCES_DIR, instance_id, "docker-compose.yml")


def _compose(instance_id: str, *args: str) -> subprocess.CompletedProcess:
    return _run(
        ["docker", "compose", "-p", f"iac-{instance_id}", "-f", _compose_path(instance_id), *args]
    )


def _ssh_port_from_compose(path: str):
    with open(path) as f:
        match = re.search(r'"(\d+):22"', f.read())
    return int(match.group(1)) if match else None


def _pick_port() -> int:
    used = set()
    for path in glob.glob(os.path.join(INSTANCES_DIR, "*", "docker-compose.yml")):
        port = _ssh_port_from_compose(path)
        if port:
            used.add(port)
    free = [p for p in range(PORT_RANGE[0], PORT_RANGE[1] + 1) if p not in used]
    if not free:
        raise ProvisioningError("Plus aucun port SSH disponible")
    return random.choice(free)


def _generate_ssh_keypair(instance_id: str) -> tuple[str, str]:
    """Retourne (clé publique, clé privée). La clé privée n'est jamais conservée sur disque."""
    os.makedirs(KEYS_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "key")
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-q"], check=True
        )
        with open(key_path) as f:
            private_key = f.read()
        with open(key_path + ".pub") as f:
            public_key = f.read().strip()

    with open(os.path.join(KEYS_DIR, f"{instance_id}.pub"), "w") as f:
        f.write(public_key + "\n")
    return public_key, private_key


def _apply_playbook(instance_id: str, public_key: str) -> None:
    """Idempotent : Ansible agit via `docker exec`, sans passer par SSH."""
    result = _run(
        [
            "ansible-playbook", ANSIBLE_PLAYBOOK,
            "-i", f"{CONTAINER_PREFIX}{instance_id},",
            "-c", "community.docker.docker",
            "-e", json.dumps({
                "pubkey": public_key,
                "ansible_python_interpreter": "/usr/bin/python3",
            }),
        ],
        timeout=120,
    )
    if result.returncode != 0:
        raise ProvisioningError(f"Échec de la configuration Ansible : {result.stdout}{result.stderr}")


# ---------- Interface publique (voir INTERFACE.md) ----------

def provision(user_id: int, distribution: str, duration_hours: int) -> dict:
    # user_id et duration_hours sont gérés côté BDD (expires_at) ;
    # ils sont conservés ici pour respecter le contrat d'interface.
    if distribution not in DISTRIBUTION_IMAGES:
        raise ProvisioningError(f"Distribution inconnue : {distribution}")

    instance_id = uuid.uuid4().hex[:8]
    try:
        return _provision(instance_id, distribution)
    except Exception:
        _cleanup(instance_id)  # ne laisse pas de conteneur orphelin
        raise


def _provision(instance_id: str, distribution: str) -> dict:
    os.makedirs(os.path.join(INSTANCES_DIR, instance_id), exist_ok=True)
    with open(TEMPLATE_PATH) as f:
        template = Template(f.read())

    # 1. Démarrage du conteneur (nouvelle tentative si le port est déjà pris sur l'hôte)
    for _ in range(3):
        ssh_port = _pick_port()
        with open(_compose_path(instance_id), "w") as f:
            f.write(template.render(
                distribution_image=DISTRIBUTION_IMAGES[distribution],
                instance_id=instance_id,
                ssh_port=ssh_port,
            ))
        result = _compose(instance_id, "up", "-d")
        if result.returncode == 0:
            break
        if "already allocated" not in result.stderr and "already in use" not in result.stderr:
            raise ProvisioningError(f"Échec du démarrage du conteneur : {result.stderr}")
    else:
        raise ProvisioningError("Impossible de réserver un port SSH")

    # 2. Clés SSH + configuration Ansible
    public_key, private_key = _generate_ssh_keypair(instance_id)
    _apply_playbook(instance_id, public_key)

    return {
        "status": "success",
        "instance_id": instance_id,
        "ssh_host": PUBLIC_HOST,
        "ssh_port": ssh_port,
        "private_key": private_key,
    }


def check_status(instance_id: str) -> dict:
    inspect = _run(
        ["docker", "inspect", "-f", "{{.State.Running}}", f"{CONTAINER_PREFIX}{instance_id}"]
    )
    if inspect.returncode != 0 or inspect.stdout.strip() != "true":
        return {"instance_id": instance_id, "status": "stopped"}

    # Le conteneur tourne : sshd répond-il ? (bannière SSH, sans authentification)
    port = _ssh_port_from_compose(_compose_path(instance_id))
    try:
        with socket.create_connection((INTERNAL_HOST, port), timeout=3) as s:
            s.settimeout(3)
            banner = s.recv(64)
        status = "running" if banner.startswith(b"SSH-") else "unreachable"
    except OSError:
        status = "unreachable"
    return {"instance_id": instance_id, "status": status}


def repair(instance_id: str) -> dict:
    # `up -d` est idempotent : relance un conteneur arrêté, le recrée s'il a disparu
    result = _compose(instance_id, "up", "-d")
    if result.returncode != 0:
        raise ProvisioningError(f"Échec de la réparation : {result.stderr}")

    with open(os.path.join(KEYS_DIR, f"{instance_id}.pub")) as f:
        public_key = f.read().strip()
    _apply_playbook(instance_id, public_key)  # réinjecte la clé si le conteneur a été recréé
    return {"instance_id": instance_id, "status": "repaired"}


def teardown(instance_id: str) -> bool:
    instance_dir = os.path.join(INSTANCES_DIR, instance_id)
    if os.path.exists(_compose_path(instance_id)):
        result = _compose(instance_id, "down", "-v")
        if result.returncode != 0:
            raise TeardownError(f"Échec du nettoyage : {result.stderr}")

    shutil.rmtree(instance_dir, ignore_errors=True)
    pub = os.path.join(KEYS_DIR, f"{instance_id}.pub")
    if os.path.exists(pub):
        os.remove(pub)
    return True


def _cleanup(instance_id: str) -> None:
    try:
        teardown(instance_id)
    except Exception:
        pass