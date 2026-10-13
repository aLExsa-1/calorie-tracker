"""HTTP 服务：JSON API + 静态前端。仅标准库实现，无第三方依赖。"""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import sys
import traceback
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .config import ConfigError
from .engine import ApiError, Engine
from .schemas import SchemaError

VERSION = "0.3.1"
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
        ("DELETE", r"/api/reports/(\d+)", lambda m, q, b: (s.delete_report(int(m[1])), (200, {"ok": True}))[1]),

        # 用户权利：数据可携带（导出）与删除（清除全部本地数据）
        ("GET", r"/api/data/export", lambda m, q, b: (200, {
            "app": "calorie-tracker", "version": VERSION,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "notice": "本文件由用户主动导出，含个人健康数据；不含任何 API Key。",
            "config": c.export_view(),
            **s.export_all(),
        })),
        ("POST", r"/api/data/clear", lambda m, q, b: (200, {
            "ok": True, "removed": s.clear_all(),
        })),
    ]


class Handler(BaseHTTPRequestHandler):
    server_version = f"CalorieTracker/{VERSION}"

    def log_message(self, fmt, *args):  # 保持控制台安静
        pass

    # ---------- 本机访问校验 ----------
    # 服务只监听回环地址，但仍需防止「设备上其他应用/浏览器页面」直接调用本接口：
    #   1) Host 头必须是回环地址 —— 阻止 DNS rebinding 从外部域名解析到 127.0.0.1；
    #   2) 若宿主设置了访问口令（安卓端由 MainActivity 随机生成并注入 WebView），
    #      则要求携带 X-CT-Token；口令为空时（电脑版直接打开浏览器）跳过校验。
    def _loopback_host(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        if host.startswith("["):                      # IPv6 字面量：[::1]:8787
            name = host[1:host.find("]")] if "]" in host else host
        elif ":" in host:
            name = host.rsplit(":", 1)[0]
        else:
            name = host
        return name in ("127.0.0.1", "localhost", "::1", "[::1]")

    def _token_ok(self) -> bool:
        token = getattr(self.server, "token", None)
        if not token:
            return True
        supplied = self.headers.get("X-CT-Token") or ""
        return secrets.compare_digest(supplied, token)

    def _cors(self):
        # 只对回环来源回显，不再使用通配符，避免任意网页跨源读取本地健康数据。
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            try:
                host = urlparse(origin).hostname or ""
            except ValueError:
                host = ""
            if host in ("127.0.0.1", "localhost", "::1"):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CT-Token")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")

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

        # 本机访问校验（见 _loopback_host / _token_ok 的说明）
        if not self._loopback_host():
            return self._send_json(403, {"error": "仅允许本机访问"})
        if not self._token_ok():
            return self._send_json(403, {"error": "缺少或错误的本机访问口令"})

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


def make_server(engine: Engine, host: str = "127.0.0.1", port: int = 8787,
                token: str | None = None) -> ThreadingHTTPServer:
    """创建 HTTP 服务。

    token 为空时不做口令校验（电脑版：用户直接在浏览器打开，天然只有本人可达）；
    安卓端由 MainActivity 传入随机口令并注入 WebView，阻止设备上其他应用调用本接口。
    """
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.engine = engine
    httpd.token = token
    return httpd
