#!/bin/sh

set -e

docker build -t cdflow-commands.test --target test .

docker run \
    --name cdflow-commands.test \
    --rm \
    -i $(tty -s && echo -t) \
    $(tty -s && echo -v $(pwd)/.hypothesis/:/usr/src/app/.hypothesis/) \
    cdflow-commands.test py.test \
        --cov=. \
        --cov-report term-missing \
        --tb=short \
        "$@"

docker run --rm cdflow-commands.test flake8 --max-complexity=5
