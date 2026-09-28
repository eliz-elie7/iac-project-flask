FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

# CLI Docker + plugin Compose (le démon reste celui de l'hôte, via le socket monté)
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker:cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose

COPY requirements.txt /code/app/requirements.txt
RUN pip install --no-cache-dir -r /code/app/requirements.txt

RUN ansible-galaxy collection install community.docker ansible.posix

COPY . /code/app

ENV PYTHONPATH=/code
ENV FLASK_APP=app.app:app

CMD ["flask", "run", "--host=0.0.0.0"]