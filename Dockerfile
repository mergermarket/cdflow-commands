FROM python:3

ENV TERRAFORM_VERSION=0.8.7
ENV TERRAGRUNT_VERSION=v0.10.2

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
     apt-transport-https \
     ca-certificates \
     curl \
     software-properties-common \
     unzip

RUN curl -fsSL https://apt.dockerproject.org/gpg | apt-key add - && \
    add-apt-repository "deb https://apt.dockerproject.org/repo/ \
       debian-$(lsb_release -cs) \
       main" && \
    apt-get update && apt-get -y install docker-engine

RUN cd /tmp && \
    curl -sSLO https://github.com/gruntwork-io/terragrunt/releases/download/${TERRAGRUNT_VERSION}/terragrunt_linux_amd64 && \
    mv terragrunt_linux_amd64 /usr/local/bin/terragrunt && \
    curl -sSLO https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform_*_linux_amd64.zip -d /usr/bin && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/* && \
    chmod 755 /usr/local/bin/terragrunt

ADD ./requirements.txt /cdflow/requirements.txt
RUN pip install -r /cdflow/requirements.txt

ADD . /cdflow

ENV PYTHONPATH=/cdflow

ENTRYPOINT ["python", "-m", "cdflow_commands"]
