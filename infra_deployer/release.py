from subprocess import check_call


class Release(object):

    def __init__(self, component_name):
        pass

    def create(self):
        image_name = '{}.dkr.ecr.{}.amazonaws.com/{}:{}'.format(
            'dummy-dev-account-id',
            'dummy-region',
            'dummy-component',
            'dev'
        )
        check_call(['docker', 'build', '-t', image_name])
