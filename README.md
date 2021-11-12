# cdflow

[![Test](https://github.com/mergermarket/cdflow-commands/actions/workflows/test.yml/badge.svg)](https://github.com/mergermarket/cdflow-commands/actions/workflows/test.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/mergermarket/cdflow-commands.svg)](https://hub.docker.com/r/mergermarket/cdflow-commands)

This repository contains the source code for the cdflow docker image, which contains the implementation of the commands that cdflow provdes - to release, deploy, and (eventually) decommission software services. This is typically used via the wrapper script at [github.com/mergermarket/cdflow/](https://github.com/mergermarket/cdflow/) in order to ensure you get the latest version when you release (with the option to pin should you need to) and that the image used remains consistent through your pipeline.

Full documentation is here: https://mergermarket.github.io/cdflow/

## Running

If you are using the [cdflow wrapper comamnd](https://github.com/mergermarket/cdflow/) mentioned above, you can get usage information by running:

```
$ cdflow --help

cdflow

Create and manage software services using continuous delivery.

Usage:
    cdflow release --platform-config <platform_config> <version> [options]
    cdflow deploy <environment> <version> [options]
    cdflow destroy <environment> [options]

Options:
    -c <component_name>, --component <component_name>
    -v, --verbose
    -p, --plan-only
```

## Running tests

```
./test.sh
```
