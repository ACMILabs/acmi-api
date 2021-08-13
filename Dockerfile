FROM python:latest

RUN apt update && apt install gunicorn3 git cron -y

COPY cronjob /var/spool/cron/crontabs/root
RUN chmod 0744 /var/spool/cron/crontabs/root
RUN crontab /var/spool/cron/crontabs/root

COPY ./requirements/base.txt /code/requirements/base.txt
RUN pip install -Ur /code/requirements/base.txt

COPY . /code/
WORKDIR /code/

CMD ["bash", "scripts/entrypoint.sh"]
