# CDFlow Commands

These are the commands available to components using CDFLow for managing the software lifecycle.

There is the facility to build a release, deploy the release and to destroy the component.

Full documentation is here: https://mergermarket.github.io/cdflow/

## Running

To get help:
```
$ ./infra/scripts/cdflow -h

CDFlow Commands.

Commands for managing the software lifecycle.

Usage:
    cdflow release [<version>] [options]
    cdflow deploy <environment> <version> [options]
    cdflow destroy <environment> [options]

Options:
    -c <component_name>, --component <component_name>
```

## Running tests

```
./test.sh
```
