# BUILD
# =====

FROM ubuntu:22.04 AS buildstep
LABEL maintainer="Richard Bullington-McGuire <richard@obscure.org>"

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y python3-dev python3-pip curl build-essential git tzdata

RUN mkdir -p /build/wheels
RUN pip3 install --upgrade pip setuptools wheel
ADD pyproject.toml /tmp/pyproject.toml
RUN cd /tmp && pip3 wheel --wheel-dir=/build/wheels .

# Now build the wheel for this project too.
ADD . /app
WORKDIR /app

RUN pip3 install build
RUN python3 -m build --wheel --outdir /build/wheels

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

# Thanks https://stackoverflow.com/a/74634740/424301 for the tip on
# using --use-deprecated=legacy-resolver
RUN pip3 install --use-deprecated=legacy-resolver /tmp/wheels/*

RUN mkdir /app
ADD alembic.ini /app

WORKDIR /app

CMD ["/bin/sh", "-c", "freezing-sync"]
