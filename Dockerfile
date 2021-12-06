FROM python:3.7-alpine
LABEL maintainer="Richard Bullington-McGuire <richard@obscure.org>"
RUN apk update
RUN apk add py3-mysqlclient git build-base
RUN addgroup -S freezing && adduser -S -G freezing freezing
RUN pip3 install --upgrade pip
ADD requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN apk del git build-base
ADD . /app
WORKDIR /app

RUN mkdir -p /data/cache/activities
RUN mkdir -p /data/cache/weather
RUN chown freezing:freezing /data/cache/activities

VOLUME /data
# We should activate this - but need to make sure the cache still works
#USER freezing
CMD freezing-sync
