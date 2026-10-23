"""前端静态托管。

前端用 BrowserRouter，`/create` 这类地址是纯客户端路由，磁盘上没有同名文件。
StaticFiles 的 html=True 只做「目录 → index.html」，深链接刷新会直接 404，
所以这里补一层 history fallback，把找不到的路径统一交回 index.html。
"""

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

# 这两个前缀属于后端，不能兜底成 HTML，否则未知接口会返回一段前端页面
_BACKEND_PREFIXES = ("api/", "events/")


class SPAMount(StaticFiles):
    """命中不到文件时回 index.html，交给前端路由处理。"""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and not path.startswith(_BACKEND_PREFIXES):
                return await super().get_response("index.html", scope)
            raise
