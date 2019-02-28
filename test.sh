#!/bin/bash

set -euo pipefail

IMAGE_ID="$(basename $(pwd))-test"

docker image build -t "${IMAGE_ID}" --target test .

if [[ "${!#}" == "--shell" ]]
then
    ARGS="bash"
else
    ARGS="py.test \
            -n auto \
            --cov=. \
            --cov-report term-missing \
            --tb=short \
            $@"
fi

docker container run \
    --name "${IMAGE_ID}" \
    --rm \
    -i $(tty -s && echo -t) \
    -v "$(pwd)":/opt/cdflow-commands \
    "${IMAGE_ID}" sh -c "${ARGS}"

docker container run --rm "${IMAGE_ID}" flake8 --max-complexity=4
