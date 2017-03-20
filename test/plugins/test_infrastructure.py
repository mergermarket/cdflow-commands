import unittest

from cdflow_commands.plugins.infrastructure import InfrastructurePlugin
from mock import ANY, Mock


class TestInfrastructurePlugin(unittest.TestCase):

    def test_plugin_does_not_build_a_release(self):
        # Given
        release_factory = Mock()

        infrastructure_plugin = InfrastructurePlugin(
            release_factory,
            deploy_factory=ANY,
            destroy_factory=ANY
        )
        # When
        infrastructure_plugin.release()

        # Then
        release_factory.assert_not_called()

    def test_plugin_runs_deploy(self):
        # Given
        deploy = Mock()

        def deploy_factory():
            return deploy

        infrastructure_plugin = InfrastructurePlugin(
            release_factory=ANY,
            deploy_factory=deploy_factory,
            destroy_factory=ANY
        )

        # When
        infrastructure_plugin.deploy()

        # Then
        deploy.run.assert_called_once()

    def test_plugin_runs_destroy(self):
        # Given
        destroy = Mock()

        def destroy_factory():
            return destroy

        infrastructure_plugin = InfrastructurePlugin(
            release_factory=ANY,
            deploy_factory=ANY,
            destroy_factory=destroy_factory
        )
        # When
        infrastructure_plugin.destroy()

        # Then
        destroy.run.assert_called_once()
