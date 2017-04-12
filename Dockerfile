FROM python:3

ENV TERRAFORM_VERSION=0.9.2

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
     apt-transport-https \
     ca-certificates \
     curl \
     software-properties-common \
     unzip && \
    curl -fsSL https://apt.dockerproject.org/gpg | apt-key add - && \
    add-apt-repository "deb https://apt.dockerproject.org/repo/ \
       debian-$(lsb_release -cs) \
       main" && \
    apt-get update && apt-get -y install docker-engine && \
    apt-get clean

RUN cd /tmp && \
    curl -sSLO https://releases.hashicorp.com/terraform/$TERRAFORM_VERSION/terraform_${TERRAFORM_VERSION}_linux_amd64.zip && \
    unzip terraform_*_linux_amd64.zip -d /usr/bin && \
    rm -rf /tmp/* && \
    rm -rf /var/tmp/*

ADD ./requirements.txt /cdflow/requirements.txt
RUN pip install -r /cdflow/requirements.txt

ADD . /cdflow

ENV PYTHONPATH=/cdflow

ENTRYPOINT ["python", "-m", "cdflow_commands"]
