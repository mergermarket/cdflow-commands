from subprocess import check_call

from collections import namedtuple


ReleaseConfig = namedtuple('ReleaseConfig', [
    'dev_account_id',
    'aws_region',
])


class Release(object):

    def __init__(self, config, component_name, version='dev'):
        self._dev_account_id = config.dev_account_id
        self._aws_region = config.aws_region
        self._component_name = component_name
        self._version = version

    def create(self):
        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            self._dev_account_id,
            self._aws_region,
            self._component_name,
            self._version
        )

        check_call(['docker', 'build', '-t', image_name])
