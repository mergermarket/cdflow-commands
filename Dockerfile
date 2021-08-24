FROM python:3.7.4-alpine3.10 AS base

ARG TERRAFORM_VERSION=0.11.15

ENV TERRAFORM_PLUGIN_DIR=/root/.terraform.d/plugins/

RUN echo http://dl-cdn.alpinelinux.org/alpine/latest-stable/main >> /etc/apk/repositories && \
    apk update && \
    apk --no-cache add curl git zip unzip wget bash

ENV DOCKER_CLI_VERSION="20.10.5"
ENV DOWNLOAD_URL="https://download.docker.com/linux/static/stable/x86_64/docker-$DOCKER_CLI_VERSION.tgz"
ENV BUILDX_URL="https://github.com/docker/buildx/releases/download/v0.5.1/buildx-v0.5.1.linux-amd64"

# install docker client
RUN mkdir -p /tmp/download && \
    curl -L $DOWNLOAD_URL | tar -xz -C /tmp/download && \
    mv /tmp/download/docker/docker /usr/local/bin/ && \
    rm -rf /tmp/download

# install buildx plugin
RUN mkdir -p ~/.docker/cli-plugins && \
    curl -sSLO  $BUILDX_URL && \
    mv  buildx-v0.5.1.linux-amd64 ~/.docker/cli-plugins/docker-buildx && \
    chmod 755 ~/.docker/cli-plugins/docker-buildx

RUN mkdir -p "${TERRAFORM_PLUGIN_DIR}" && cd /tmp && \
    curl -sSLO "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" && \
        unzip "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" -d /usr/bin/ && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

RUN mkdir -p /opt/cdflow-commands/cdflow_commands && \
    pip install pipenv
WORKDIR /opt/cdflow-commands/

ENV PYTHONPATH=/opt/cdflow-commands

COPY Pipfile Pipfile.lock ./
RUN apk add --no-cache --virtual .build-deps \
    gcc musl-dev libffi-dev openssl-dev && \
    pipenv install --deploy --system && \
    apk del --no-cache .build-deps

FROM base AS test

ENV AWS_ACCESS_KEY_ID dummy
ENV AWS_SECRET_ACCESS_KEY dummy

COPY Pipfile Pipfile.lock ./
RUN apk add --no-cache --virtual .build-deps \
    gcc musl-dev libffi-dev openssl-dev && \
    pipenv install --deploy --system --dev && \
    apk del --no-cache .build-deps

COPY ./cdflow_commands /opt/cdflow-commands/cdflow_commands/
COPY ./test /opt/cdflow-commands/test/

FROM base

COPY ./cdflow_commands /opt/cdflow-commands/cdflow_commands/

LABEL type="platform"

ENTRYPOINT ["python", "-m", "cdflow_commands"]
