"""静态托管：前端深链接要回 index.html，后端前缀不能被兜底吞掉。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.staticfiles import SPAMount

INDEX = "<html>INDEX</html>"


def _app(tmp_path) -> TestClient:
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.css").write_text("body{}")

    app = FastAPI()

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"api": "ok"}

    app.mount("/", SPAMount(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_root_serves_index(tmp_path):
    client = _app(tmp_path)

    response = client.get("/")

    assert response.status_code == 200
    assert response.text == INDEX


def test_deep_link_falls_back_to_index(tmp_path):
    """刷新 /create、/editor/xxx 不能 404，否则分享出去的链接全打不开。"""
    client = _app(tmp_path)

    for path in ("/create", "/editor/abc", "/marketing/abc", "/batch"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text == INDEX, path


def test_real_files_are_served_as_is(tmp_path):
    client = _app(tmp_path)

    response = client.get("/assets/app.css")

    assert response.status_code == 200
    assert response.text == "body{}"


def test_known_api_route_still_wins(tmp_path):
    client = _app(tmp_path)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"api": "ok"}


def test_unknown_api_route_returns_json_not_html(tmp_path):
    """打错的接口要返回 404 JSON，不能被兜底成一段 HTML。"""
    client = _app(tmp_path)

    response = client.get("/api/typo")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
