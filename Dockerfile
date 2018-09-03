FROM python:3.7.0-alpine3.8 AS base

ENV TERRAFORM_VERSION=0.11.7

ENV TERRAFORM_PROVIDER_LOGENTRIES_VERSION=0.1.0_logset_datasource
ENV TERRAFORM_PROVIDER_ACME_VERSION=0.6.0

ENV TERRAFORM_PLUGIN_DIR=/root/.terraform.d/plugins/

RUN echo http://dl-cdn.alpinelinux.org/alpine/latest-stable/main >> /etc/apk/repositories
RUN apk update
RUN apk --no-cache add gcc musl-dev libffi-dev openssl-dev docker curl git zip unzip wget libc6-compat

RUN mkdir -p "${TERRAFORM_PLUGIN_DIR}" && cd /tmp && \
    curl -sSLO "https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" && \
        unzip "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" -d /usr/bin/ && \
    wget -q "https://s3-eu-west-1.amazonaws.com/mmg-terraform-providers/terraform-provider-logentries_v${TERRAFORM_PROVIDER_LOGENTRIES_VERSION}_linux_amd64.zip" && \
        unzip "terraform-provider-logentries_v${TERRAFORM_PROVIDER_LOGENTRIES_VERSION}_linux_amd64.zip" -d "${TERRAFORM_PLUGIN_DIR}" && \
    wget -q "https://github.com/paybyphone/terraform-provider-acme/releases/download/v${TERRAFORM_PROVIDER_ACME_VERSION}/terraform-provider-acme_v${TERRAFORM_PROVIDER_ACME_VERSION}_linux_amd64.zip" && \
        unzip "terraform-provider-acme_v${TERRAFORM_PROVIDER_ACME_VERSION}_linux_amd64.zip" -d "${TERRAFORM_PLUGIN_DIR}" && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

RUN mkdir -p /opt/cdflow-commands/cdflow_commands
WORKDIR /opt/cdflow-commands/

ENV PYTHONPATH=/opt/cdflow-commands

COPY ./requirements.txt ./requirements.txt
RUN pip install -r ./requirements.txt

FROM base AS test

COPY test_requirements.txt .
RUN pip install --no-cache-dir -r test_requirements.txt

COPY ./cdflow_commands /opt/cdflow-commands/cdflow_commands/
COPY ./test /opt/cdflow-commands/test/

FROM base

COPY ./cdflow_commands /opt/cdflow-commands/cdflow_commands/

ENTRYPOINT ["python", "-m", "cdflow_commands"]
