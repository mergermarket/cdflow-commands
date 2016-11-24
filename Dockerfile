# Used to create docker image for running the commands invoked by the stubs in ../scripts/.

FROM centos:7

ENV TERRAFORM_VERSION=0.7.11
ENV TERRAGRUNT_VERSION=v0.1.4
ENV DOCKER_VERSION=1.12.3-1.el7.centos

ADD yum.repos.d/docker.repo /etc/yum.repos.d/
ADD ./requirements.txt /infra/requirements.txt

RUN rpm -iUvh http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-8.noarch.rpm && \
    yum install -y bash ca-certificates curl docker-engine-${DOCKER_VERSION} gawk git git openssl python-pip unzip wget && \
    cd /tmp && \
    curl -sSLO https://github.com/gruntwork-io/terragrunt/releases/download/${TERRAGRUNT_VERSION}/terragrunt_linux_amd64 && \
    mv terragrunt_linux_amd64 /usr/local/bin/terragrunt && \
    curl -sSLO https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform_*_linux_amd64.zip -d /usr/bin && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/* && \
    chmod 755 /usr/local/bin/terragrunt && \
    yum group install -y "Development Tools" && yum install -y python-devel && \
    pip install -r /infra/requirements.txt && \
    yum group remove "Development Tools" -y && yum clean all

ADD . /infra
