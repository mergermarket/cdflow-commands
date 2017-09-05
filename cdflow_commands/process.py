from cdflow_commands.exceptions import UserFacingError
from cdflow_commands.logger import logger

from subprocess import CalledProcessError, check_call as _check_call


def check_call(*args, **kwargs):
    try:
        _check_call(*args, **kwargs)
    except CalledProcessError as e:
        raise UserFacingError(e)
