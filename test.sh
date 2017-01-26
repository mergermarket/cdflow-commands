#!/bin/sh

set -e

docker build -t infra-deployer.test -f Dockerfile.test .

docker run \
    --name infra-deployer.test \
    --rm \
    -i $(tty -s && echo -t) \
    infra-deployer.test py.test \
        --cov=. \
        --cov-report term-missing \
        "$@"

docker run --rm infra-deployer.test flake8 --max-complexity=4

