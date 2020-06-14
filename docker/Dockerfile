FROM python:3.7-alpine

LABEL maintainer="Samuel Gratzl <sam@sgratzl.com>"

VOLUME "/backup"
WORKDIR /backup

RUN pip --no-cache-dir install slack-cleaner2

CMD ["python", "-"]