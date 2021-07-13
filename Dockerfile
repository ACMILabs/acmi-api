FROM python:latest

RUN apt update && apt install gunicorn3 -y

COPY ./requirements/base.txt /code/requirements/base.txt
RUN pip install -Ur /code/requirements/base.txt

COPY . /code/
WORKDIR /code/

CMD ["bash", "scripts/entrypoint.sh"]
