# BUILD
# =====

FROM ubuntu:22.04 AS buildstep
LABEL maintainer="Richard Bullington-McGuire <richard@obscure.org>"

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y python3-dev python3-pip curl build-essential git tzdata

RUN mkdir -p /build/wheels
RUN pip3 install --upgrade pip setuptools wheel
ADD requirements.txt /tmp/requirements.txt
RUN pip3 wheel -r /tmp/requirements.txt --wheel-dir=/build/wheels

# Now build the wheel for this project too.
ADD . /app
WORKDIR /app

RUN python3 setup.py bdist_wheel -d /build/wheels

# DEPLOY
# =====

FROM ubuntu:22.04 as deploystep
LABEL maintainer="Richard Bullington-McGuire <richard@obscure.org>"

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y curl tzdata \
  && apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip --no-install-recommends \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip setuptools wheel
RUN mkdir -p /data/cache/activities
RUN mkdir -p /data/cache/weather

VOLUME /data

COPY --from=buildstep /build/wheels /tmp/wheels

RUN pip3 install /tmp/wheels/*

RUN mkdir /app
ADD alembic.ini /app

WORKDIR /app

CMD ['freezing-sync']
