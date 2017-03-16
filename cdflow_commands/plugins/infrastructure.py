from cdflow_commands.plugins import Plugin


class InfrastructurePlugin(Plugin):
    def __init__(
        self, release_factory, deploy_factory,
        destroy_factory
    ):
        self.release_factory = release_factory
        self.deploy_factory = deploy_factory
        self.destroy_factory = destroy_factory

    def release(self):
        pass

    def deploy(self):
        deploy = self.deploy_factory()
        deploy.run()

    def destroy(self):
        destroy = self.destroy_factory()
        destroy.run()
