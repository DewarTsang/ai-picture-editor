from functools import lru_cache

from langchain_core.utils.function_calling import convert_to_openai_function
from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from app.config import get_settings
from app.tools import SPECS, ToolSpec

# 图像模型必须走 DashScope 原生接口，纯文本的规划模型可用 OpenAI 兼容模式
_COMPATIBLE_PATH = "/compatible-mode/v1"


class PlannerUnavailable(Exception):
    """规划模型未配置或不可用。"""


def explain(exc: Exception) -> str | None:
    """把模型服务的已知报错翻成用户看得懂、能自己动手解决的一句话。

    不认识的异常返回 None，交给上层按未知故障记录完整堆栈。
    """
    if isinstance(exc, AuthenticationError):
        return "规划模型鉴权失败，请检查 DASHSCOPE_API_KEY 是否正确"
    if isinstance(exc, RateLimitError):
        return "规划模型请求过于频繁，请稍后再试"
    if isinstance(exc, PermissionDeniedError):
        if _is_quota(exc):
            return "规划模型额度已用尽，请在百炼控制台充值或关闭「仅使用免费额度」后重试"
        return "规划模型拒绝了本次请求，请稍后再试"
    if isinstance(exc, APIStatusError):
        return f"规划模型服务返回错误（HTTP {exc.status_code}），请稍后再试"
    if isinstance(exc, APIConnectionError):
        return "规划模型连接失败，请检查网络后重试"
    return None


def _is_quota(exc: Exception) -> bool:
    """免费额度耗尽与普通权限拒绝都走 403，只能靠响应体里的额度码区分。"""
    body = str(getattr(exc, "body", "") or "").lower()
    message = str(getattr(exc, "message", "") or "").lower()
    return "quota" in body or "quota" in message or "额度" in message


def _schema_of(spec: ToolSpec) -> dict:
    function = convert_to_openai_function(spec.params)
    function["name"] = spec.name
    function["description"] = spec.description

    parameters = function.get("parameters", {})
    for hidden in spec.agent_hidden:
        parameters.get("properties", {}).pop(hidden, None)
    parameters["required"] = [
        name for name in parameters.get("required", []) if name not in spec.agent_hidden
    ]
    return {"type": "function", "function": function}


@lru_cache
def planner():
    """绑定全部已注册工具的规划模型。工具增减无需改动此处。"""
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise PlannerUnavailable("未配置 DASHSCOPE_API_KEY，对话指令不可用")

    model = ChatOpenAI(
        model=settings.planner_model,
        api_key=settings.dashscope_api_key,
        base_url=f"{settings.dashscope_base_url}{_COMPATIBLE_PATH}",
        temperature=0,
    )
    return model.bind_tools([_schema_of(spec) for spec in SPECS])
