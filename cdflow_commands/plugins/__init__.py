from abc import ABC, abstractmethod


class Plugin(ABC):
    @abstractmethod
    def __init__(self, release_factory, deploy_factory, destroy_factory):
        pass

    @abstractmethod
    def release(self):
        pass

    @abstractmethod
    def deploy(self):
        pass

    @abstractmethod
    def destroy(self):
        pass
