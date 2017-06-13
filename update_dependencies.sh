#!/bin/bash

set -euo pipefail

for REQUIREMENTS_IN in requirements test_requirements
do
docker run --rm -v "$(pwd)":"$(pwd)" -w "$(pwd)" python:3 \
    sh -c "pip install -r ${REQUIREMENTS_IN}.in && echo Automatically generated: ${REQUIREMENTS_IN} > ${REQUIREMENTS_IN}.txt && pip freeze > ${REQUIREMENTS_IN}.txt"
done
