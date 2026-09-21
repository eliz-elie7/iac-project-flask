FROM python:3.12-slim

WORKDIR /code

COPY requirements.txt /code/app/requirements.txt
RUN pip install --no-cache-dir -r /code/app/requirements.txt

COPY . /code/app

ENV PYTHONPATH=/code
ENV FLASK_APP=app.app:app

CMD ["flask", "run", "--host=0.0.0.0"]