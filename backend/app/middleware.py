"""请求日志：逐条打印方法、路径、状态、耗时与出入参体。

写成纯 ASGI 中间件而不是 BaseHTTPMiddleware，避免缓冲响应体，
/events 的 SSE 长连接才能边推边发。
"""

import json
import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.request")

# 单条日志里出入参最多留这么多字符，超出截断
MAX_BODY = 2000
# 命中这些字段名的值一律脱敏
SENSITIVE = {"password", "token", "authorization", "cookie", "secret", "api_key"}
# 采样上限，避免大文件上传把内存吃满
MAX_CAPTURE = 64 * 1024


class RequestLogger:
    """给每个请求打一条汇总日志，出错时连堆栈一起打出来。"""

    def __init__(self, app: ASGIApp, *, with_body: bool = True) -> None:
        self.app = app
        self.with_body = with_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()
        status = 500
        request_body = b""
        response_body = b""
        # SSE 一直在推，攒不出完整响应体，也不值得等它结束
        streaming = False

        async def capture_request() -> Message:
            nonlocal request_body
            message = await receive()
            if message["type"] == "http.request" and len(request_body) < MAX_CAPTURE:
                request_body += message.get("body", b"")
            return message

        async def capture_response(message: Message) -> None:
            nonlocal status, response_body, streaming
            if message["type"] == "http.response.start":
                status = message["status"]
                streaming = _is_event_stream(message.get("headers", []))
                headers = [*message.get("headers", []), (b"x-request-id", request_id.encode())]
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body" and not streaming:
                response_body += message.get("body", b"")
            await send(message)

        try:
            await self.app(scope, capture_request, capture_response)
        except Exception:
            logger.exception(
                "请求异常 %s %s request_id=%s", scope["method"], scope["path"], request_id
            )
            raise
        finally:
            self._log(scope, status, request_id, started, request_body, response_body, streaming)

    def _log(
        self,
        scope: Scope,
        status: int,
        request_id: str,
        started: float,
        request_body: bytes,
        response_body: bytes,
        streaming: bool,
    ) -> None:
        if self.with_body:
            for label, body in (("请求", request_body), ("响应", response_body)):
                text = _describe(body)
                if text:
                    logger.info("  %s体 %s", label, text)
        query = scope.get("query_string", b"").decode("utf-8", "replace")
        target = scope["path"] + (f"?{query}" if query else "")
        logger.info(
            "%s %s -> %s %.0fms request_id=%s",
            scope["method"],
            target,
            status,
            (time.perf_counter() - started) * 1000,
            request_id,
        )


def _is_event_stream(headers: list[tuple[bytes, bytes]]) -> bool:
    return any(
        key.lower() == b"content-type" and b"event-stream" in value.lower()
        for key, value in headers
    )


def _describe(body: bytes) -> str:
    """把报文体压成一行，JSON 里的敏感字段脱敏，非 JSON 按原文截断。"""
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except ValueError:
        return body[:MAX_BODY].decode("utf-8", "replace")
    return json.dumps(_redact(payload), ensure_ascii=False)[:MAX_BODY]


def _redact(payload: object) -> object:
    if isinstance(payload, dict):
        return {
            key: ("***" if str(key).lower() in SENSITIVE else _redact(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_redact(item) for item in payload]
    return payload
