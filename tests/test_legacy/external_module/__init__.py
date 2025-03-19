from logging import LoggerAdapter
from typing import Any

from cellophane import pre_hook


def mocked() -> str:
    return "external_module.mocked WAS CALLED"

def non_mocked() -> str:
    return "external_module.non_mocked WAS CALLED"

@pre_hook()
def external_hook(logger: LoggerAdapter, **_: Any) -> None:
    logger.info("external_module.external_hook WAS CALLED")
    logger.info(mocked())
    logger.info(non_mocked())