FROM python:3-alpine

ENV TERRAFORM_VERSION=0.9.10
ENV ACME_VERSION=0.3.0

RUN echo http://dl-cdn.alpinelinux.org/alpine/latest-stable/community >> /etc/apk/repositories
RUN apk update
RUN apk add gcc musl-dev libffi-dev openssl-dev docker curl git

RUN cd /tmp && \
    curl -sSLO https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform_*_linux_amd64.zip -d /usr/bin && \
    curl -sSLO https://github.com/paybyphone/terraform-provider-acme/releases/download/v${ACME_VERSION}/terraform-provider-acme_v${ACME_VERSION}_linux_amd64.zip && \
    unzip terraform-provider-acme_*_linux_amd64.zip -d /usr/bin && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

ADD ./requirements.txt /cdflow/requirements.txt
RUN pip install -r /cdflow/requirements.txt

ADD . /cdflow
ADD terraformrc /root/.terraformrc

ENV PYTHONPATH=/cdflow

ENTRYPOINT ["python", "-m", "cdflow_commands"]
