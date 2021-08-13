FROM python:latest

RUN apt update && apt install gunicorn3 git cron -y

RUN apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
RUN echo "deb https://dl.k6.io/deb stable main" | tee /etc/apt/sources.list.d/k6.list
RUN apt update && apt install k6 -y

COPY cronjob /var/spool/cron/crontabs/root
RUN chmod 0744 /var/spool/cron/crontabs/root
RUN crontab /var/spool/cron/crontabs/root

COPY ./requirements/base.txt /code/requirements/base.txt
COPY ./requirements/test.txt /code/requirements/test.txt
RUN pip install -Ur /code/requirements/test.txt

COPY . /code/
WORKDIR /code/

CMD ["bash", "scripts/entrypoint.sh"]
