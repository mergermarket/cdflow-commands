import unittest

from cdflow_commands.plugins.aws_lambda import LambdaPlugin
from mock import Mock, ANY


class TestLambdaPlugin(unittest.TestCase):

    def test_plugin_runs_release(self):
        # Given
        release = Mock()

        def release_factory():
            return release

        ecs_plugin = LambdaPlugin(
            release_factory,
            deploy_factory=ANY,
            destroy_factory=ANY,
        )
        # When
        ecs_plugin.release()

        # Then
        release.create.assert_called_once()

    def test_plugin_runs_deploy(self):
        # Given
        deploy = Mock()

        def deploy_factory():
            return deploy

        ecs_plugin = LambdaPlugin(
            release_factory=ANY,
            deploy_factory=deploy_factory,
            destroy_factory=ANY,
        )

        # When
        ecs_plugin.deploy()

        # Then
        deploy.run.assert_called_once()
