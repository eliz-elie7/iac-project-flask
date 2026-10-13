import os
import glob
import json
import random
import shutil
import socket
import subprocess
import tempfile
import threading
import time

import requests
from flask import Flask, request, jsonify
from jinja2 import Template

app = Flask(__name__)

WORKER_HOSTNAME = os.environ["WORKER_HOSTNAME"]            # ex: "worker1", nom du service Docker Compose
WORKER_IP = os.environ.get("WORKER_IP", WORKER_HOSTNAME)   # résolu via le réseau Docker interne
CONTROLLER_URL = os.environ["CONTROLLER_URL"]               # ex: "http://web:5000"
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", 20))
INTERNAL_HOST = "127.0.0.1"     # l'agent tourne nativement sur la VM, plus dans un conteneur cherchant à joindre son hôte

INSTANCES_DIR = "/data/instances"
TEMPLATE_PATH = "/data/instances/templates/docker-compose.template.yml"
ANSIBLE_PLAYBOOK = "/data/ansible/playbooks/configure_instance.yml"
KEYS_DIR = "/data/instances/keys"
PORT_RANGE = (22000, 22999)

worker_id = None  # attribué par le Controller lors de l'enregistrement


class ProvisioningError(Exception):
    pass


# ---------- Enregistrement + heartbeat ----------

def _system_metrics():
    cpu_count = os.cpu_count() or 1
    mem_total_kb = 0
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                    break
    except FileNotFoundError:
        pass
    return {"cpu": f"{cpu_count} vCPU", "memory": f"{mem_total_kb // 1024} MB"}


def register_with_controller():
    global worker_id
    while worker_id is None:
        try:
            resp = requests.post(
                f"{CONTROLLER_URL}/workers/register",
                json={"hostname": WORKER_HOSTNAME, "ip": WORKER_IP, **_system_metrics()},
                timeout=5,
            )
            resp.raise_for_status()
            worker_id = resp.json()["worker_id"]
            print(f"[worker-agent] Enregistré sous l'id {worker_id}")
        except requests.RequestException as e:
            print(f"[worker-agent] Échec d'enregistrement, nouvel essai dans 5s : {e}")
            time.sleep(5)


def heartbeat_loop():
    while True:
        if worker_id is not None:
            try:
                requests.post(
                    f"{CONTROLLER_URL}/workers/heartbeat",
                    json={"worker_id": worker_id, "status": "AVAILABLE", **_system_metrics()},
                    timeout=5,
                )
            except requests.RequestException as e:
                print(f"[worker-agent] Échec du heartbeat : {e}")
        time.sleep(HEARTBEAT_INTERVAL)


# ---------- Provisioning (repris de l'ancien orchestrator.py) ----------

def _compose_path(instance_id):
    return os.path.join(INSTANCES_DIR, instance_id, "docker-compose.yml")


def _compose(instance_id, *args):
    return subprocess.run(
        ["docker", "compose", "-p", f"iac-{instance_id}", "-f", _compose_path(instance_id), *args],
        capture_output=True, text=True,
    )


def _pick_port():
    used = set()
    for path in glob.glob(os.path.join(INSTANCES_DIR, "*", "docker-compose.yml")):
        with open(path) as f:
            for line in f:
                if '":22"' in line:
                    used.add(int(line.strip().strip('"').split(":")[0]))
    free = [p for p in range(PORT_RANGE[0], PORT_RANGE[1] + 1) if p not in used]
    if not free:
        raise ProvisioningError("Plus aucun port SSH disponible sur ce Worker")
    return random.choice(free)


def _generate_ssh_keypair(instance_id):
    os.makedirs(KEYS_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        key_path = os.path.join(tmp, "key")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", key_path, "-N", "", "-q"], check=True)
        with open(key_path) as f:
            private_key = f.read()
        with open(f"{key_path}.pub") as f:
            public_key = f.read().strip()
    with open(os.path.join(KEYS_DIR, f"{instance_id}.pub"), "w") as f:
        f.write(public_key + "\n")
    return public_key, private_key


def _apply_playbook(instance_id, public_key):
    result = subprocess.run(
        [
            "ansible-playbook", ANSIBLE_PLAYBOOK,
            "-i", f"instance-{instance_id},",
            "-c", "community.docker.docker",
            "-e", json.dumps({"pubkey": public_key, "ansible_python_interpreter": "/usr/bin/python3"}),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise ProvisioningError(f"Échec Ansible : {result.stdout}{result.stderr}")


# ---------- API interne (appelée par le Resource Manager du Controller) ----------

@app.route("/internal/provision", methods=["POST"])
def provision():
    data = request.get_json()
    instance_id, docker_image = data["instance_id"], data["docker_image"]

    os.makedirs(os.path.join(INSTANCES_DIR, instance_id), exist_ok=True)
    with open(TEMPLATE_PATH) as f:
        template = Template(f.read())

    for _ in range(3):
        ssh_port = _pick_port()
        with open(_compose_path(instance_id), "w") as f:
            f.write(template.render(distribution_image=docker_image, instance_id=instance_id, ssh_port=ssh_port))
        result = _compose(instance_id, "up", "-d")
        if result.returncode == 0:
            break
        if "already allocated" not in result.stderr and "already in use" not in result.stderr:
            return jsonify({"error": result.stderr}), 500
    else:
        return jsonify({"error": "Impossible de réserver un port SSH"}), 500

    try:
        public_key, private_key = _generate_ssh_keypair(instance_id)
        _apply_playbook(instance_id, public_key)
    except ProvisioningError as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "instance_id": instance_id,
        "container_id": f"instance-{instance_id}",
        "ssh_host": WORKER_IP,
        "ssh_port": ssh_port,
        "private_key": private_key,
    })


@app.route("/internal/status/<instance_id>", methods=["GET"])
def status(instance_id):
    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", f"instance-{instance_id}"],
        capture_output=True, text=True,
    )
    if inspect.returncode != 0 or inspect.stdout.strip() != "true":
        return jsonify({"status": "stopped"})

    port = None
    with open(_compose_path(instance_id)) as f:
        for line in f:
            if '":22"' in line:
                port = int(line.strip().strip('"').split(":")[0])
    try:
        with socket.create_connection((INTERNAL_HOST, port), timeout=3) as s:
            s.settimeout(3)
            banner = s.recv(64)
        result = "running" if banner.startswith(b"SSH-") else "unreachable"
    except OSError:
        result = "unreachable"
    return jsonify({"status": result})


@app.route("/internal/repair/<instance_id>", methods=["POST"])
def repair(instance_id):
    result = _compose(instance_id, "up", "-d")
    if result.returncode != 0:
        return jsonify({"error": result.stderr}), 500
    with open(os.path.join(KEYS_DIR, f"{instance_id}.pub")) as f:
        public_key = f.read().strip()
    try:
        _apply_playbook(instance_id, public_key)
    except ProvisioningError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"status": "repaired"})


@app.route("/internal/teardown/<instance_id>", methods=["POST"])
def teardown(instance_id):
    if os.path.exists(_compose_path(instance_id)):
        result = _compose(instance_id, "down", "-v")
        if result.returncode != 0:
            return jsonify({"error": result.stderr}), 500
    shutil.rmtree(os.path.join(INSTANCES_DIR, instance_id), ignore_errors=True)
    pub = os.path.join(KEYS_DIR, f"{instance_id}.pub")
    if os.path.exists(pub):
        os.remove(pub)
    return jsonify({"status": "removed"})


@app.route("/internal/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "worker_id": worker_id})


if __name__ == "__main__":
    threading.Thread(target=register_with_controller, daemon=True).start()
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=6000)