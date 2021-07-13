FROM python:latest

COPY ./requirements/base.txt /code/requirements/base.txt
COPY ./requirements/test.txt /code/requirements/test.txt
RUN pip install -Ur /code/requirements/test.txt

COPY . /code/
WORKDIR /code/

CMD ["bash", "scripts/entrypoint.sh"]
