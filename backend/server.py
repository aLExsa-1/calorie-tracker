"""HTTP 服务：JSON API + 静态前端。仅标准库实现，无第三方依赖。"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .config import ConfigError
from .engine import ApiError, Engine
from .schemas import SchemaError

VERSION = "0.2.1"
WEB_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _day(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ApiError(400, f"日期格式应为 YYYY-MM-DD：{value}")


def _entry_id(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ApiError(400, "记录 id 必须是整数")


MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 单张解码后 5 MB
ALLOWED_MIME = ("image/jpeg", "image/png", "image/webp", "image/gif")


def _images(value) -> list[dict]:
    """校验前端提交的图片：data URL 或 {mime, data}。返回 [{mime, data}]（纯 base64）。"""
    if value in (None, "", []):
        return []
    if not isinstance(value, list):
        raise ApiError(400, "images 必须是数组")
    if len(value) > MAX_IMAGES:
        raise ApiError(400, f"最多上传 {MAX_IMAGES} 张图片")
    out = []
    for i, item in enumerate(value):
        raw = item if isinstance(item, str) else str(item.get("data") or "") if isinstance(item, dict) else ""
        mime = (item.get("mime") if isinstance(item, dict) else None) or ""
        if raw.startswith("data:"):
            head, _, raw = raw.partition(",")
            mime = head[5:].split(";")[0] or mime
        mime = str(mime).lower()
        if mime not in ALLOWED_MIME:
            raise ApiError(400, f"第 {i + 1} 张图片格式不支持（仅 jpg/png/webp/gif）")
        import base64
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (ValueError, TypeError):
            raise ApiError(400, f"第 {i + 1} 张图片不是合法 base64")
        if not decoded:
            raise ApiError(400, f"第 {i + 1} 张图片为空")
        if len(decoded) > MAX_IMAGE_BYTES:
            raise ApiError(400, f"第 {i + 1} 张图片超过 5 MB，请压缩后再上传")
        out.append({"mime": mime, "data": raw})
    return out

def _report_or_404(store, rid: int) -> dict:
    report = store.get_report(rid)
    if report is None:
        raise ApiError(404, "报告不存在")
    return report


# ---------------- 路由 ----------------
def _routes(e: Engine):
    c = e.config
    s = e.store
    return [
        ("GET", r"/api/health", lambda m, q, b: (200, {"ok": True, "version": VERSION})),

        ("GET", r"/api/config", lambda m, q, b: (200, c.public())),
        ("PUT", r"/api/config/search", lambda m, q, b: (c.set_search(b), (200, c.public()))[1]),
        ("POST", r"/api/config/llm", lambda m, q, b: (c.upsert_llm(b), (200, c.public()))[1]),
        ("DELETE", r"/api/config/llm/([\w-]+)", lambda m, q, b: (c.delete_llm(m[1]), (200, c.public()))[1]),
        ("POST", r"/api/config/llm/([\w-]+)/activate", lambda m, q, b: (c.activate_llm(m[1]), (200, c.public()))[1]),
        ("PUT", r"/api/config/task-llm", lambda m, q, b: (c.set_task_llm(b), (200, c.public()))[1]),
        ("PUT", r"/api/config/prompts/(\w+)", lambda m, q, b: (c.set_prompt(m[1], b), (200, c.public()))[1]),
        ("DELETE", r"/api/config/prompts/(\w+)", lambda m, q, b: (c.reset_prompt(m[1]), (200, c.public()))[1]),
        ("POST", r"/api/llm/test", lambda m, q, b: (200, e.test_llm(b.get("id")))),
        ("POST", r"/api/search/test", lambda m, q, b: (200, e.test_search(str(b.get("query") or "")))),

        ("GET", r"/api/profile", lambda m, q, b: (200, {"profile": e.profile_on(_day(q.get("date")))})),
        ("GET", r"/api/profile/history", lambda m, q, b: (200, {"history": s.profile_history()})),
        ("PUT", r"/api/profile", lambda m, q, b: (200, {"profile": e.update_profile(b)})),
        ("POST", r"/api/profile/estimate-metabolism",
         lambda m, q, b: (200, e.estimate_metabolism(_day(b.get("date"))))),

        ("POST", r"/api/estimate/food",
         lambda m, q, b: (200, e.estimate_food(str(b.get("text") or ""), _day(b.get("date")), b.get("meal"),
                                              images=_images(b.get("images"))))),
        ("POST", r"/api/estimate/activity",
         lambda m, q, b: (200, e.estimate_activity(str(b.get("text") or ""), _day(b.get("date"))))),

        ("GET", r"/api/entries", lambda m, q, b: (200, {"entries": [
            e._entry_view(r) for r in s.list_entries(q.get("start") or q.get("date") or date.today().isoformat(),
                                                    q.get("end") or q.get("date") or date.today().isoformat())]})),
        ("POST", r"/api/entries",
         lambda m, q, b: (201, {"entries": e.save_entries(_day(b.get("date")), b.get("items") or [])})),
        ("PUT", r"/api/entries/(\d+)", lambda m, q, b: (200, {"entry": e.update_entry(_entry_id(m[1]), b)})),
        ("DELETE", r"/api/entries/(\d+)", lambda m, q, b: (e.delete_entry(_entry_id(m[1])), (200, {"ok": True}))[1]),

        ("GET", r"/api/days/([\d-]+)", lambda m, q, b: (200, e.day_summary(_day(m[1])))),

        ("POST", r"/api/reports",
         lambda m, q, b: (200, e.report(b.get("period", "week"), _day(b.get("date")), bool(b.get("analyze"))))),
        ("GET", r"/api/reports", lambda m, q, b: (200, {"reports": s.list_reports()})),
        ("GET", r"/api/reports/(\d+)", lambda m, q, b: (200, _report_or_404(s, int(m[1])))),
    ]


class Handler(BaseHTTPRequestHandler):
    server_version = f"CalorieTracker/{VERSION}"

    def log_message(self, fmt, *args):  # 保持控制台安静
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "请求体不是合法 JSON")
        if not isinstance(value, dict):
            raise ApiError(400, "请求体必须是 JSON 对象")
        return value

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if not path.startswith("/api/"):
            return self._static(path)
        query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        try:
            body = self._read_body() if method in ("POST", "PUT") else {}
            for verb, pattern, fn in _routes(self.server.engine):
                if verb != method:
                    continue
                match = re.fullmatch(pattern, path)
                if match:
                    status, payload = fn(match, query, body)
                    return self._send_json(status, payload)
            return self._send_json(404, {"error": f"接口不存在：{method} {path}"})
        except ApiError as exc:
            return self._send_json(exc.status, {"error": exc.message, "detail": exc.detail})
        except ConfigError as exc:
            return self._send_json(400, {"error": str(exc)})
        except SchemaError as exc:
            return self._send_json(422, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - 兜底，避免服务崩溃
            traceback.print_exc(file=sys.stderr)
            return self._send_json(500, {"error": f"服务器内部错误：{exc}"})

    def _static(self, path: str) -> None:
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if not target.is_relative_to(WEB_DIR.resolve()) or not target.is_file():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)


def make_server(engine: Engine, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.engine = engine
    return httpd
