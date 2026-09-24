import json
import os
import shlex
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
    instance_dir = os.path.join(INSTANCES_DIR, instance_id)
    os.makedirs(instance_dir, exist_ok=True)

    # 1. Générer le docker-compose.yml de l'instance à partir du template
    # (le port hôte n'est pas fixé ici : Docker en assigne un librement côté hôte,
    #  car le choisir depuis le conteneur web n'aurait aucune garantie de validité)
    with open(TEMPLATE_PATH) as f:
        template = Template(f.read())

    compose_content = template.render(
        distribution_image=DISTRIBUTION_IMAGES[distribution],
        instance_id=instance_id,
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

    # 2bis. Relire le port réellement assigné par Docker côté hôte
    port_result = subprocess.run(
        ["docker", "compose", "-f", compose_path, "port", "instance", "22"],
        capture_output=True, text=True
    )
    if port_result.returncode != 0 or not port_result.stdout.strip():
        raise ProvisioningError(f"Impossible de déterminer le port SSH assigné : {port_result.stderr}")
    ssh_port = int(port_result.stdout.strip().rsplit(":", 1)[-1])

    # 3. Générer la paire de clés SSH
    public_key, private_key = _generate_ssh_keypair(instance_id)
    public_key = " ".join(public_key.split())

    # 4. Configurer via Ansible (injection de la clé, idempotent)
    inventory_path = os.path.join(instance_dir, "inventory.ini")
    with open(inventory_path, "w") as f:
        f.write(
            f"[instance]\n"
            f"target ansible_host=host.docker.internal ansible_port={ssh_port} "
            "ansible_user=root ansible_python_interpreter=/usr/bin/python3 "
            "ansible_ssh_private_key_file=ansible/files/provisioning_key\n"
        )

    ansible_result = subprocess.run(
        [
            "ansible-playbook", ANSIBLE_PLAYBOOK,
            "-i", inventory_path,
            "--extra-vars", json.dumps({"pubkey": public_key}),
        ],
        capture_output=True, text=True
    )
    if ansible_result.returncode != 0:
        details = "\n".join(
            output for output in (ansible_result.stdout, ansible_result.stderr)
            if output and output.strip()
        ).strip()
        if not details:
            details = f"ansible-playbook a échoué avec le code {ansible_result.returncode} sans sortie."
        raise ProvisioningError(f"Échec de la configuration Ansible : {details}")

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

    with open("ansible/files/provisioning_key.pub") as f:
        provisioning_key = " ".join(f.read().split())
    restore_key = (
        "mkdir -p /root/.ssh && chmod 700 /root/.ssh; "
        "touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys; "
        f"grep -qxF {shlex.quote(provisioning_key)} /root/.ssh/authorized_keys || "
        f"printf '%s\\n' {shlex.quote(provisioning_key)} >> /root/.ssh/authorized_keys"
    )
    restore_result = subprocess.run(
        ["docker", "exec", f"instance-{instance_id}", "sh", "-c", restore_key],
        capture_output=True, text=True
    )
    if restore_result.returncode != 0:
        raise ProvisioningError(
            f"Impossible de restaurer la clé de réparation : {restore_result.stderr.strip()}"
        )

    port_result = subprocess.run(
        ["docker", "compose", "-f", compose_path, "port", "instance", "22"],
        capture_output=True, text=True
    )
    if port_result.returncode != 0 or not port_result.stdout.strip():
        raise ProvisioningError(f"Impossible de déterminer le port SSH assigné : {port_result.stderr}")
    ssh_port = int(port_result.stdout.strip().rsplit(":", 1)[-1])

    # Ré-application du playbook — idempotent, ne change pas la clé existante
    key_path = os.path.join(KEYS_DIR, f"{instance_id}.pub")
    with open(key_path) as f:
        public_key = " ".join(f.read().split())

    inventory_path = os.path.join(INSTANCES_DIR, instance_id, "inventory.ini")
    with open(inventory_path, "w") as f:
        f.write(
            f"[instance]\n"
            f"target ansible_host=host.docker.internal ansible_port={ssh_port} "
            "ansible_user=root ansible_python_interpreter=/usr/bin/python3 "
            "ansible_ssh_private_key_file=ansible/files/provisioning_key\n"
        )

    ansible_result = subprocess.run(
        [
            "ansible-playbook", ANSIBLE_PLAYBOOK,
            "-i", inventory_path,
            "--extra-vars", json.dumps({"pubkey": public_key}),
        ],
        capture_output=True, text=True
    )
    if ansible_result.returncode != 0:
        details = (ansible_result.stderr or ansible_result.stdout).strip()
        raise ProvisioningError(f"Échec de la réparation Ansible : {details}")
    return {"instance_id": instance_id, "status": "repaired", "ssh_port": ssh_port}


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