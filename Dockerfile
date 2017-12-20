FROM python:3-alpine3.6

ENV TERRAFORM_VERSION=0.11.0

ENV TERRAFORM_PROVIDER_AWS_VERSION=1.5.0
ENV TERRAFORM_PROVIDER_FASTLY_VERSION=0.1.2_le-support
ENV TERRAFORM_PROVIDER_LOGENTRIES_VERSION=0.1.0_logset_datasource
ENV TERRAFORM_PROVIDER_NULL_VERSION=1.0.0
ENV TERRAFORM_PROVIDER_TEMPLATE_VERSION=1.0.0
ENV TERRAFORM_PROVIDER_ACME_VERSION=0.3.0
ENV TERRAFORM_PROVIDER_EXTERNAL_VERSION=1.0.0

RUN echo http://dl-cdn.alpinelinux.org/alpine/latest-stable/main >> /etc/apk/repositories
RUN apk update
RUN apk -U add gcc musl-dev libffi-dev openssl-dev docker curl git zip unzip wget

RUN cd /tmp && \
    curl -sSLO https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
        unzip terraform_*_linux_amd64.zip -d /usr/bin && \
    curl -sSLO https://releases.hashicorp.com/terraform-provider-aws/$TERRAFORM_PROVIDER_AWS_VERSION/terraform-provider-aws_${TERRAFORM_PROVIDER_AWS_VERSION}_linux_amd64.zip && \
        unzip terraform-provider-aws_*_linux_amd64.zip -d /usr/bin && \
    wget -q https://s3-eu-west-1.amazonaws.com/mmg-terraform-providers/terraform-provider-fastly_v${TERRAFORM_PROVIDER_FASTLY_VERSION}_linux_amd64.zip && \
        unzip terraform-provider-fastly_*_linux_amd64.zip -d /usr/bin && \
    wget -q https://s3-eu-west-1.amazonaws.com/mmg-terraform-providers/terraform-provider-logentries_v${TERRAFORM_PROVIDER_LOGENTRIES_VERSION}_linux_amd64.zip && \
        unzip terraform-provider-logentries_*_linux_amd64.zip -d /usr/bin && \
    curl -sSLO https://releases.hashicorp.com/terraform-provider-null/$TERRAFORM_PROVIDER_NULL_VERSION/terraform-provider-null_${TERRAFORM_PROVIDER_NULL_VERSION}_linux_amd64.zip && \
        unzip terraform-provider-null_*_linux_amd64.zip -d /usr/bin && \
    curl -sSLO https://releases.hashicorp.com/terraform-provider-template/$TERRAFORM_PROVIDER_TEMPLATE_VERSION/terraform-provider-template_${TERRAFORM_PROVIDER_TEMPLATE_VERSION}_linux_amd64.zip && \
        unzip terraform-provider-template_*_linux_amd64.zip -d /usr/bin && \
    wget -q https://github.com/paybyphone/terraform-provider-acme/releases/download/v${TERRAFORM_PROVIDER_ACME_VERSION}/terraform-provider-acme_v${TERRAFORM_PROVIDER_ACME_VERSION}_linux_amd64.zip && \
        unzip terraform-provider-acme_*_linux_amd64.zip -d /usr/bin && \
    curl -sSLO https://releases.hashicorp.com/terraform-provider-external/$TERRAFORM_PROVIDER_EXTERNAL_VERSION/terraform-provider-external_${TERRAFORM_PROVIDER_EXTERNAL_VERSION}_linux_amd64.zip && \
        unzip terraform-provider-external_*_linux_amd64.zip -d /usr/bin && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

COPY ./requirements.txt /cdflow/requirements.txt
RUN pip install -r /cdflow/requirements.txt

COPY . /cdflow
COPY terraformrc /root/.terraformrc

ENV PYTHONPATH=/cdflow

ENTRYPOINT ["python", "-m", "cdflow_commands"]
