# Procedure de demonstration

Cette procedure permet de verifier les quatre parties du projet : Flask, PostgreSQL, Ansible/SSH et la haute disponibilite des instances.

## 1. Demarrer le projet

Depuis WSL :

```bash
cd ~/iac-project-flask
docker compose up -d --build
docker compose ps
```

Les services `web` et `db` doivent etre en statut `Up`.

Verifier Flask :

```bash
curl http://localhost:5000/login
```

Le resultat attendu est une reponse HTTP `200`.

## 2. Creer un compte

Ouvrir dans le navigateur :

```text
http://localhost:5000/register
```

Creer un compte, puis se connecter depuis :

```text
http://localhost:5000/login
```

## 3. Louer une instance

Depuis le dashboard :

1. Cliquer sur **Louer une nouvelle instance**.
2. Choisir `ubuntu-22.04` ou `debian-12`.
3. Choisir une duree.
4. Valider la location.

La page de resultat affiche l'identifiant de l'instance, le port SSH et la cle privee.

Copier la cle dans un fichier local :

```bash
nano ID_INSTANCE.pem
chmod 600 ID_INSTANCE.pem
```

Remplacer `ID_INSTANCE` par l'identifiant affiche dans le dashboard.

## 4. Tester la connexion SSH

Utiliser la commande affichee par Flask :

```bash
ssh -i ID_INSTANCE.pem -p PORT root@127.0.0.1
```

Dans l'instance :

```bash
whoami
hostname
cat /etc/os-release
exit
```

Resultat attendu :

```text
root
Ubuntu 22.04 ou Debian 12
```

## 5. Verifier les conteneurs et la base

Depuis un autre terminal :

```bash
docker ps
```

Les conteneurs `web`, `db` et `instance-ID_INSTANCE` doivent apparaitre.

Verifier les locations en base :

```bash
docker compose exec db psql -U iac_user -d iac_project -c \
"SELECT * FROM rental;"
```

## 6. Tester la reparation automatique

Arreter volontairement une instance :

```bash
docker stop instance-ID_INSTANCE
```

Le scheduler Flask verifie les instances toutes les 30 secondes. Attendre environ 30 secondes, puis verifier :

```bash
docker ps --filter name=instance-ID_INSTANCE
```

Recuperer le nouveau port SSH :

```bash
docker compose -f instances/ID_INSTANCE/docker-compose.yml port instance 22
```

Verifier l'etat en base :

```bash
docker compose exec db psql -U iac_user -d iac_project -c \
"SELECT r.instance_id, s.last_status, s.repair_attempts, s.ssh_port
 FROM rental r
 JOIN instance_state s ON s.rental_id = r.id
 WHERE r.instance_id='ID_INSTANCE';"
```

Resultat attendu :

```text
last_status       | running
repair_attempts   | 1 ou plus
```

Se reconnecter avec le nouveau port :

```bash
ssh -i ID_INSTANCE.pem -p NOUVEAU_PORT root@127.0.0.1
```

## 7. Tester la suppression d'une instance

Utiliser une instance de test pour ne pas supprimer une vraie location :

```bash
docker compose exec web python3 -c \
"from app import orchestrator; print(orchestrator.teardown('ID_INSTANCE'))"
```

Resultat attendu :

```text
True
```

Verifier que le conteneur a disparu :

```bash
docker ps -a --filter name=instance-ID_INSTANCE
```

## 8. Commandes de diagnostic

Logs Flask :

```bash
docker compose logs --tail=100 web
```

Logs PostgreSQL :

```bash
docker compose logs --tail=100 db
```

Etat general :

```bash
docker compose ps
docker ps
```

## Resultat final attendu

La demonstration doit montrer :

- la creation et la connexion a un compte Flask ;
- la location d'une instance selon sa distribution et sa duree ;
- la connexion SSH avec une cle privee ;
- la configuration de la cle par Ansible ;
- la detection d'une panne et la reparation automatique ;
- la suppression d'une instance avec `teardown()`.
