# CDFlow Commands

These are the commands available to components using CDFLow for managing the software lifecycle.

There is the facility to build a release, deploy the release and to destroy the component.

Full documentation is here: https://mergermarket.github.io/cdflow/

## Running

To get help:
```
$ cdflow --help

CDFlow Commands.

Commands for managing the software lifecycle.

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
