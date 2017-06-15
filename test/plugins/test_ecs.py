import unittest

from cdflow_commands.exceptions import MissingArgumentError
from cdflow_commands.plugins.ecs import ECSPlugin, build_ecs_plugin

from mock import ANY, Mock


class TestECSPlugin(unittest.TestCase):

    def test_plugin_runs_deploy(self):
        # Given
        deploy = Mock()

        def deploy_factory():
            return deploy

        ecs_plugin = ECSPlugin(
            release_factory=ANY,
            deploy_factory=deploy_factory,
            destroy_factory=ANY,
            deploy_monitor_factory=Mock()
        )

        # When
        ecs_plugin.deploy()

        # Then
        deploy.run.assert_called_once()

    def test_plugin_runs_destroy(self):
        # Given
        destroy = Mock()

        def destroy_factory():
            return destroy

        ecs_plugin = ECSPlugin(
            release_factory=ANY,
            deploy_factory=ANY,
            destroy_factory=destroy_factory,
            deploy_monitor_factory=ANY
        )
        # When
        ecs_plugin.destroy()

        # Then
        destroy.run.assert_called_once()

    def test_plugin_monitors_the_deploy(self):
        # Given
        deploy_monitor = Mock()

        def deploy_monitor_factory():
            return deploy_monitor

        ecs_plugin = ECSPlugin(
            release_factory=ANY,
            deploy_factory=Mock(),
            destroy_factory=ANY,
            deploy_monitor_factory=deploy_monitor_factory
        )

        # When
        ecs_plugin.deploy()

        # Then
        deploy_monitor.wait.assert_called_once()

    def test_plugin_fails_to_build_when_version_missing(self):
        # Given
        version = ''

        # Then
        with self.assertRaises(MissingArgumentError):
            build_ecs_plugin(ANY, ANY, version, ANY, ANY, ANY)

    def test_plugin_fails_to_build_when_environment_missing(self):
        # Given
        environment = ''

        # Then
        with self.assertRaises(MissingArgumentError):
            build_ecs_plugin(environment, ANY, ANY, ANY, ANY, ANY)
