FROM python:3.7.1-alpine3.8 AS base

ENV TERRAFORM_VERSION=0.11.10

ENV K8SVERSION=v1.8.11

RUN echo http://dl-cdn.alpinelinux.org/alpine/latest-stable/main >> /etc/apk/repositories && \
    apk update && \
    apk --no-cache add gcc musl-dev libffi-dev openssl-dev docker curl git unzip && \
    curl -o /usr/local/bin/kubectl https://amazon-eks.s3-us-west-2.amazonaws.com/1.10.3/2018-07-26/bin/linux/amd64/kubectl && \
    chmod +x /usr/local/bin/kubectl && \
    curl -o /usr/local/bin/aws-iam-authenticator  https://amazon-eks.s3-us-west-2.amazonaws.com/1.10.3/2018-07-26/bin/linux/amd64/aws-iam-authenticator && \
    chmod +x /usr/local/bin/aws-iam-authenticator && \
    cd /tmp && \
    curl -sSLO "https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" && \
    unzip "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" -d /usr/bin/ && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/* && \
    mkdir -p /opt/cdflow-commands/cdflow_commands && \
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

RUN pip uninstall pipenv -y && \
    rm Pipfile Pipfile.lock && \
    apk del gcc musl-dev libffi-dev openssl-dev curl unzip && \
    rm -rf /var/cache/apk/*

ENTRYPOINT ["python", "-m", "cdflow_commands"]
