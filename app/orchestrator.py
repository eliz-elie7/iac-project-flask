import os
import subprocess
import uuid
from datetime import datetime
from jinja2 import Template

INSTANCES_DIR = "instances"
TEMPLATE_PATH = "instances/templates/docker-compose.template.yml"
ANSIBLE_PLAYBOOK = "ansible/playbooks/configure_instance.yml"
KEYS_DIR = "instances/keys"

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


def _generate_ssh_keypair(instance_id: str) -> tuple[str, str]:
    """Génère une paire de clés SSH dédiée. Retourne (public_key, private_key)."""
    os.makedirs(KEYS_DIR, exist_ok=True)
    key_path = os.path.join(KEYS_DIR, instance_id)

    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-q"],
        check=True
    )

    with open(f"{key_path}.pub") as f:
        public_key = f.read().strip()
    with open(key_path) as f:
        private_key = f.read()

    return public_key, private_key


def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def provision(user_id: int, distribution: str, duration_hours: int) -> dict:
    if distribution not in DISTRIBUTION_IMAGES:
        raise ProvisioningError(f"Distribution inconnue : {distribution}")

    instance_id = uuid.uuid4().hex[:8]
    ssh_port = _find_free_port()
    instance_dir = os.path.join(INSTANCES_DIR, instance_id)
    os.makedirs(instance_dir, exist_ok=True)

    # 1. Générer le docker-compose.yml de l'instance à partir du template
    with open(TEMPLATE_PATH) as f:
        template = Template(f.read())

    compose_content = template.render(
        distribution_image=DISTRIBUTION_IMAGES[distribution],
        instance_id=instance_id,
        ssh_port=ssh_port,
    )
    compose_path = os.path.join(instance_dir, "docker-compose.yml")
    with open(compose_path, "w") as f:
        f.write(compose_content)

    # 2. Lancer le conteneur
    result = subprocess.run(
        ["docker", "compose", "-f", compose_path, "up", "-d"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise ProvisioningError(f"Échec du démarrage du conteneur : {result.stderr}")

    # 3. Générer la paire de clés SSH
    public_key, private_key = _generate_ssh_keypair(instance_id)

    # 4. Configurer via Ansible (injection de la clé, idempotent)
    inventory_line = f"instance ansible_host=127.0.0.1 ansible_port={ssh_port} ansible_user=root"
    ansible_result = subprocess.run(
        [
            "ansible-playbook", ANSIBLE_PLAYBOOK,
            "-i", inventory_line + ",",
            "--extra-vars", f"pubkey='{public_key}'",
        ],
        capture_output=True, text=True
    )
    if ansible_result.returncode != 0:
        raise ProvisioningError(f"Échec de la configuration Ansible : {ansible_result.stderr}")

    return {
        "status": "success",
        "instance_id": instance_id,
        "ssh_host": "127.0.0.1",
        "ssh_port": ssh_port,
        "private_key": private_key,
    }


def check_status(instance_id: str, ssh_host: str, ssh_port: int) -> dict:
    result = subprocess.run(
        [
            "ssh", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=no",
            "-p", str(ssh_port), f"root@{ssh_host}", "true"
        ],
        capture_output=True
    )
    status = "running" if result.returncode == 0 else "unreachable"
    return {"instance_id": instance_id, "status": status}


def repair(instance_id: str) -> dict:
    compose_path = os.path.join(INSTANCES_DIR, instance_id, "docker-compose.yml")
    result = subprocess.run(
        ["docker", "compose", "-f", compose_path, "restart"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise ProvisioningError(f"Échec du redémarrage : {result.stderr}")

    # Ré-application du playbook — idempotent, ne change pas la clé existante
    key_path = os.path.join(KEYS_DIR, f"{instance_id}.pub")
    with open(key_path) as f:
        public_key = f.read().strip()

    subprocess.run(
        [
            "ansible-playbook", ANSIBLE_PLAYBOOK,
            "--extra-vars", f"pubkey='{public_key}'",
        ],
        capture_output=True, text=True
    )
    return {"instance_id": instance_id, "status": "repaired"}


def teardown(instance_id: str) -> bool:
    compose_path = os.path.join(INSTANCES_DIR, instance_id, "docker-compose.yml")
    result = subprocess.run(
        ["docker", "compose", "-f", compose_path, "down", "-v"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise TeardownError(f"Échec du nettoyage : {result.stderr}")

    # Nettoyage des clés SSH et du dossier de l'instance
    for ext in ("", ".pub"):
        key_file = os.path.join(KEYS_DIR, f"{instance_id}{ext}")
        if os.path.exists(key_file):
            os.remove(key_file)

    return True