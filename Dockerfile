FROM python:3.7.4-alpine3.10 AS base

ENV TERRAFORM_VERSION=0.11.14

ENV TERRAFORM_PLUGIN_DIR=/root/.terraform.d/plugins/

ENV K8SVERSION=1.13.7
ENV K8SVERSIONDATE=2019-06-11

RUN echo http://dl-cdn.alpinelinux.org/alpine/latest-stable/main >> /etc/apk/repositories && \
    apk update && \
    apk --no-cache add curl git zip unzip wget bash

ENV DOCKER_CLI_VERSION="18.06.1-ce"
ENV DOWNLOAD_URL="https://download.docker.com/linux/static/stable/x86_64/docker-$DOCKER_CLI_VERSION.tgz"

# install docker client
RUN mkdir -p /tmp/download && \
    curl -L $DOWNLOAD_URL | tar -xz -C /tmp/download && \
    mv /tmp/download/docker/docker /usr/local/bin/ && \
    rm -rf /tmp/download

RUN cd /tmp && \
    curl -o kubectl https://amazon-eks.s3-us-west-2.amazonaws.com/${K8SVERSION}/${K8SVERSIONDATE}/bin/linux/amd64/kubectl && \
    chmod +x ./kubectl && \
    mv ./kubectl /usr/local/bin/kubectl

RUN cd /tmp && \
    curl -o aws-iam-authenticator https://amazon-eks.s3-us-west-2.amazonaws.com/${K8SVERSION}/${K8SVERSIONDATE}/bin/linux/amd64/aws-iam-authenticator && \
    chmod +x ./aws-iam-authenticator && \
    mv ./aws-iam-authenticator /usr/local/bin/aws-iam-authenticator

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

ENTRYPOINT ["python", "-m", "cdflow_commands"]
