FROM python:3.12-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io \
        docker-cli \
        ansible \
        openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /code/app/requirements.txt
RUN pip install --no-cache-dir -r /code/app/requirements.txt

COPY . /code/app

ENV PYTHONPATH=/code
ENV FLASK_APP=app.app:app

CMD ["flask", "run", "--host=0.0.0.0"]
