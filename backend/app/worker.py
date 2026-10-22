import logging

from arq.connections import RedisSettings

from app import logsetup
from app.config import get_settings
from app.tasks import TASKS

logger = logging.getLogger(__name__)

settings = get_settings()

logsetup.setup()


async def startup(ctx: dict) -> None:
    """启动时把生效的模型名打出来。

    .env 改了模型必须重启 worker 才生效，配置缓存在进程里，
    日志里能直接看到当前跑的是哪个模型，省得对着 404 猜。
    """
    logger.info(
        "模型配置 文生图=%s 图像编辑=%s 规划=%s",
        settings.text_to_image_model,
        settings.image_edit_model,
        settings.planner_model,
    )


class WorkerSettings:
    """ARQ worker 入口。新增异步任务需在 app.tasks.TASKS 中注册。"""

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = TASKS
    on_startup = startup
    max_jobs = 4
    job_timeout = 300
    keep_result = 3600
