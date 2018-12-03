FROM python:3.7.1-alpine3.8 AS base

ENV TERRAFORM_VERSION=0.11.10

ENV TERRAFORM_PLUGIN_DIR=/root/.terraform.d/plugins/

ENV K8SVERSION=v1.8.11

RUN echo http://dl-cdn.alpinelinux.org/alpine/latest-stable/main >> /etc/apk/repositories
RUN apk update
RUN apk --no-cache add gcc musl-dev libffi-dev openssl-dev docker curl git zip unzip wget libc6-compat

RUN cd /tmp && \
    curl -o kubectl https://amazon-eks.s3-us-west-2.amazonaws.com/1.10.3/2018-07-26/bin/linux/amd64/kubectl && \
    chmod +x ./kubectl && \
    mv ./kubectl /usr/local/bin/kubectl

RUN cd /tmp && \
    curl -o aws-iam-authenticator  https://amazon-eks.s3-us-west-2.amazonaws.com/1.10.3/2018-07-26/bin/linux/amd64/aws-iam-authenticator && \
    chmod +x ./aws-iam-authenticator && \
    mv ./aws-iam-authenticator /usr/local/bin/aws-iam-authenticator

RUN mkdir -p "${TERRAFORM_PLUGIN_DIR}" && cd /tmp && \
    curl -sSLO "https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" && \
        unzip "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" -d /usr/bin/ && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

RUN mkdir -p /opt/cdflow-commands/cdflow_commands && \
    pip install pipenv
WORKDIR /opt/cdflow-commands/

ENV PYTHONPATH=/opt/cdflow-commands

COPY Pipfile Pipfile.lock ./
RUN pipenv install --deploy --system

FROM base AS test

ENV AWS_ACCESS_KEY_ID dummy
ENV AWS_SECRET_ACCESS_KEY dummy

COPY Pipfile Pipfile.lock ./
RUN pipenv install --deploy --system --dev

COPY ./cdflow_commands /opt/cdflow-commands/cdflow_commands/
COPY ./test /opt/cdflow-commands/test/

FROM base

COPY ./cdflow_commands /opt/cdflow-commands/cdflow_commands/

ENTRYPOINT ["python", "-m", "cdflow_commands"]
