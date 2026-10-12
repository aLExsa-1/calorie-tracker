"""本地模拟 LLM + 搜索服务，用于端到端测试（不联网、不花钱）。

- POST /v1/chat/completions  OpenAI 兼容协议：根据 system 提示词里的任务类型返回固定 JSON
- POST /v1/messages          Anthropic 协议
- GET  /search?q=...         模拟 SearXNG 搜索
- 每次请求都把收到的请求体记录到 self.requests，测试里可以检查提示词是否正确拼接
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


def _reply_for(system: str, user: str) -> str:
    if "饮食" in user or "食物" in system:
        return json.dumps({
            "items": [
                {"name": "米饭", "grams": 150, "kcal": 174, "protein_g": 3.9, "carb_g": 38.9, "fat_g": 0.5,
                 "confidence": "high", "basis": "一碗约 150g"},
                {"name": "鸡蛋", "grams": 100, "kcal": 144, "protein_g": 12.6, "carb_g": 1.5, "fat_g": 9.5,
                 "confidence": "high", "basis": "两个约 100g"},
            ],
            "notes": "模拟估算",
        }, ensure_ascii=False)
    if "运动" in user and "运动描述" in user:
        return json.dumps({
            "items": [{"name": "快走", "minutes": 40, "kcal": 120, "basis": "MET 4.3 扣除静息后估算"}],
            "notes": "模拟估算",
        }, ensure_ascii=False)
    if "基础代谢" in system or "身体数据" in user and "维持" in system:
        return json.dumps({"bmr_kcal": 1600, "maintenance_kcal": 2080, "basis": "模拟：Mifflin 估算后乘 1.3"},
                          ensure_ascii=False)
    if "统计时段" in user:
        return json.dumps({
            "summary": "模拟分析：饮食蛋白质偏低，运动量尚可。",
            "diet_score": 70, "exercise_score": 65, "exercise_level": "规律",
            "diet_comments": ["蛋白质摄入略低"], "exercise_comments": ["每周运动接近推荐量"],
            "suggestions": ["每餐加一份蛋白质"], "risks": [],
        }, ensure_ascii=False)
    if "connectivity" in system:
        return '{"ok": true}'
    return "{}"


class MockState:
    def __init__(self):
        self.requests: list[dict] = []
        self.fail_next = 0          # 让接下来 N 次请求返回 500
        self.bad_json_next = 0      # 让接下来 N 次返回非法 JSON 内容


def make_handler(state: MockState):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/search":
                q = parse_qs(url.query).get("q", [""])[0]
                state.requests.append({"kind": "search", "q": q})
                return self._json(200, {"results": [
                    {"title": "模拟来源：米饭热量", "url": "https://example.test/rice",
                     "content": "米饭每100克约116千卡。"},
                    {"title": "模拟来源：鸡蛋热量", "url": "https://example.test/egg",
                     "content": "鸡蛋每100克约144千卡。"},
                ]})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            auth = self.headers.get("Authorization") or self.headers.get("x-api-key") or ""
            state.requests.append({"kind": "llm", "path": self.path, "auth": auth, "body": body})

            if state.fail_next > 0:
                state.fail_next -= 1
                return self._json(500, {"error": {"message": "mock upstream failure"}})

            if self.path.endswith("/chat/completions"):
                msgs = body.get("messages", [])
                system = next((m["content"] for m in msgs if m["role"] == "system"), "")
                user = next((m["content"] for m in msgs if m["role"] == "user"), "")
                text = "这不是 JSON" if state.bad_json_next > 0 else _reply_for(system, user)
                if state.bad_json_next > 0:
                    state.bad_json_next -= 1
                return self._json(200, {"choices": [{"message": {"role": "assistant", "content": text}}]})

            if self.path.endswith("/messages"):
                system = body.get("system", "")
                user = body["messages"][0]["content"]
                text = _reply_for(system, user)
                return self._json(200, {"content": [{"type": "text", "text": text}]})

            self._json(404, {"error": "not found"})

    return H


class MockServer:
    def __init__(self, port: int = 0):
        self.state = MockState()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self.state))
        self.port = self.httpd.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
