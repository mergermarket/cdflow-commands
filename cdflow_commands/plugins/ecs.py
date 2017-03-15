from cdflow_commands.plugins import Plugin


class ECSPlugin(Plugin):
    def __init__(
        self, release_factory, deploy_factory,
        destroy_factory, deploy_monitor_factory
    ):
        self.release_factory = release_factory
        self.deploy_factory = deploy_factory
        self.destroy_factory = destroy_factory
        self.deploy_monitor_factory = deploy_monitor_factory

    def release(self):
        release = self.release_factory()
        release.create()

    def deploy(self):
        deploy = self.deploy_factory()
        deploy.run()
        monitor = self.deploy_monitor_factory()
        monitor.wait()

    def destroy(self):
        destroy = self.destroy_factory()
        destroy.run()
