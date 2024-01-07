FROM grafana/k6:latest AS k6official

FROM python:alpine

COPY --from=k6official /usr/bin/k6 /usr/bin/k6

RUN apk add --update git openssh make

COPY cronjob /etc/crontabs/root

COPY ./requirements/base.txt /code/requirements/base.txt
COPY ./requirements/test.txt /code/requirements/test.txt
RUN pip install -Ur /code/requirements/test.txt

COPY . /code/
WORKDIR /code/

CMD ["scripts/entrypoint.sh"]
