#!/bin/sh

set -e

docker build -t cdflow-commands.test -f Dockerfile.test .

docker run \
    --name cdflow-commands.test \
    --rm \
    -i $(tty -s && echo -t) \
    $(tty -s && echo -v $(pwd)/.hypothesis/:/usr/src/app/.hypothesis/) \
    cdflow-commands.test py.test \
        -n auto \
        --cov=. \
        --cov-report term-missing \
        --tb=short \
        "$@"

docker run --rm cdflow-commands.test flake8 --max-complexity=4
