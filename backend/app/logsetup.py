"""统一日志配置。

uvicorn 只配了它自己的 logger，应用侧的 logger 不挂 handler 就只会落到
Python 的「最后兜底」上，级别和格式都不受控；worker 进程没有 uvicorn，
同样得自己配一份，所以入口两边都调这里。
"""

import logging

from app.config import get_settings

_FORMAT = "%(asctime)s %(levelname)-5s %(name)s | %(message)s"


def setup() -> None:
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format=_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
