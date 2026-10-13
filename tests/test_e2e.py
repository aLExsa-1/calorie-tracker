"""端到端测试：真实后端（HTTP）+ 模拟 LLM/搜索服务。运行：python -m unittest tests.test_e2e -v"""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend.config import Config  # noqa: E402
from backend.engine import Engine  # noqa: E402
from backend.server import make_server  # noqa: E402
from backend.store import Store  # noqa: E402
from mock_llm import MockServer  # noqa: E402


def call(base, method, path, body=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    send = {"Content-Type": "application/json"}
    send.update(headers or {})
    req = urllib.request.Request(base + path, data=data, method=method, headers=send)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def call_tok(base, token, method, path, body=None):
    """带本机访问口令调用（安卓端的调用方式）。"""
    return call(base, method, path, body, headers={"X-CT-Token": token})


class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 测试数据放在工作区内（系统临时目录在本环境下 SQLite 无法建库）
        cls.data = ROOT / "tests" / ".data" / f"run-{threading.get_ident()}"
        cls.data.mkdir(parents=True, exist_ok=True)
        cls.mock = MockServer().start()
        cls.engine = Engine(Store(cls.data / "ct.db"), Config(cls.data / "config.json"))
        cls.httpd = make_server(cls.engine, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.engine.store.close()
        cls.mock.stop()

    def setUp(self):
        self.mock.state.requests.clear()
        self.mock.state.fail_next = 0
        self.mock.state.bad_json_next = 0

    # --- helpers
    def add_llm(self, name="mock-openai", protocol="openai", model="mock-model", base=None, key="sk-test-1234abcd",
                extra=""):
        base = base or (self.mock.base + "/v1")
        s, body = call(self.base, "POST", "/api/config/llm", {
            "name": name, "protocol": protocol, "model": model, "base_url": base,
            "api_key": key, "temperature": 0.2, "max_tokens": 2048, "extra_body": extra,
        })
        self.assertEqual(s, 200, body)
        return next(p["id"] for p in body["llm_profiles"] if p["name"] == name)

    # ---------------- 配置 ----------------
    def test_health_and_static_index_free(self):
        s, body = call(self.base, "GET", "/api/health")
        self.assertEqual(s, 200)
        self.assertTrue(body["ok"])

    def test_health_version_is_0_3_1(self):
        s, body = call(self.base, "GET", "/api/health")
        self.assertEqual(s, 200)
        self.assertEqual(body["version"], "0.3.1")

    def test_changelog_json_served(self):
        import json as _json
        import urllib.request
        with urllib.request.urlopen(self.base + "/changelog.json", timeout=5) as r:
            data = _json.loads(r.read().decode("utf-8"))
        self.assertEqual(data["version"], "0.3.1")
        self.assertTrue(len(data["items"]) >= 1)
    def test_llm_profile_crud_masks_key(self):
        pid = self.add_llm("A")
        s, cfg = call(self.base, "GET", "/api/config")
        p = next(x for x in cfg["llm_profiles"] if x["id"] == pid)
        self.assertNotIn("api_key", p)
        self.assertTrue(p["api_key_set"])
        self.assertEqual(p["api_key_hint"], "…abcd")
        # 编辑时留空 Key 保持不变
        s, _ = call(self.base, "POST", "/api/config/llm", {
            "id": pid, "name": "A2", "protocol": "openai", "model": "m2",
            "base_url": self.mock.base + "/v1", "api_key": "",
        })
        self.assertEqual(s, 200)
        stored = self.engine.config.llm_full(pid)
        self.assertEqual(stored["api_key"], "sk-test-1234abcd")
        self.assertEqual(stored["name"], "A2")
        s, _ = call(self.base, "DELETE", f"/api/config/llm/{pid}")
        self.assertEqual(s, 200)

    def test_llm_validation(self):
        s, body = call(self.base, "POST", "/api/config/llm", {
            "name": "x", "protocol": "gemini", "model": "m", "base_url": "https://a"})
        self.assertEqual(s, 400)
        s, body = call(self.base, "POST", "/api/config/llm", {
            "name": "x", "protocol": "openai", "model": "m", "base_url": "ftp://a"})
        self.assertEqual(s, 400)
        self.assertIn("http", body["error"])
        s, body = call(self.base, "POST", "/api/config/llm", {
            "name": "x", "protocol": "openai", "model": "m", "base_url": "https://a", "extra_body": "{bad"})
        self.assertEqual(s, 400)

    def test_prompt_override_and_reset(self):
        s, _ = call(self.base, "PUT", "/api/config/prompts/food_estimate", {
            "system": "自定义系统提示", "user": "饮食：{input}", "use_search": False, "search_query": ""})
        self.assertEqual(s, 200)
        s, cfg = call(self.base, "GET", "/api/config")
        self.assertEqual(cfg["prompts"]["food_estimate"]["system"], "自定义系统提示")
        s, _ = call(self.base, "DELETE", "/api/config/prompts/food_estimate")
        s, cfg = call(self.base, "GET", "/api/config")
        self.assertNotEqual(cfg["prompts"]["food_estimate"]["system"], "自定义系统提示")

    # ---------------- AI 估算 ----------------
    def test_food_estimate_with_search_and_custom_prompt(self):
        pid = self.add_llm("food-llm")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        call(self.base, "PUT", "/api/config/search", {"provider": "searxng", "base_url": self.mock.base})
        s, _ = call(self.base, "PUT", "/api/config/prompts/food_estimate", {
            "system": "你是食物估算器。", "user": "饮食描述：{input}；餐次：{meal}；{search}",
            "use_search": True, "search_query": "{input} 热量"})
        s, body = call(self.base, "POST", "/api/estimate/food", {
            "text": "米饭一碗，两个鸡蛋", "date": "2026-09-01", "meal": "早餐"})
        self.assertEqual(s, 200, body)
        self.assertEqual([i["name"] for i in body["items"]], ["米饭", "鸡蛋"])
        self.assertTrue(body["search_used"])
        self.assertEqual(body["items"][0]["meal"], "早餐")
        # 检查请求：搜索被调用，且搜索结果被拼进提示词
        searches = [r for r in self.mock.state.requests if r["kind"] == "search"]
        self.assertTrue(searches and "米饭" in searches[0]["q"])
        llm_req = next(r for r in self.mock.state.requests if r["kind"] == "llm")
        user_msg = llm_req["body"]["messages"][1]["content"]
        self.assertIn("米饭一碗，两个鸡蛋", user_msg)
        self.assertIn("模拟来源：米饭热量", user_msg)
        self.assertEqual(llm_req["body"]["messages"][0]["content"].split("\n")[0], "你是食物估算器。")
        self.assertIn("只输出一个 JSON 对象", llm_req["body"]["messages"][0]["content"])
        self.assertTrue(llm_req["auth"].startswith("Bearer sk-test"))

    def test_search_failure_degrades_gracefully(self):
        pid = self.add_llm("food-llm-2")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        call(self.base, "PUT", "/api/config/search", {"provider": "searxng", "base_url": "http://127.0.0.1:9"})
        s, body = call(self.base, "POST", "/api/estimate/food", {"text": "米饭", "date": "2026-09-01"})
        self.assertEqual(s, 200, body)
        self.assertFalse(body["search_used"])
        self.assertTrue(any("联网搜索失败" in w for w in body["warnings"]))
        call(self.base, "PUT", "/api/config/search", {"provider": "none"})

    def test_activity_estimate_anthropic_protocol(self):
        pid = self.add_llm("anthropic-llm", protocol="anthropic", model="claude-x",
                           base=self.mock.base, key="ant-key-9999")
        s, _ = call(self.base, "PUT", "/api/config/task-llm", {"activity_estimate": pid})
        self.assertEqual(s, 200)
        s, body = call(self.base, "POST", "/api/estimate/activity", {"text": "快走40分钟", "date": "2026-09-01"})
        self.assertEqual(s, 200, body)
        self.assertEqual(body["items"][0]["name"], "快走")
        self.assertEqual(body["items"][0]["kcal"], 120)
        req = next(r for r in self.mock.state.requests if r["path"].endswith("/messages"))
        self.assertEqual(req["auth"], "ant-key-9999")
        call(self.base, "PUT", "/api/config/task-llm", {})

    def test_extra_body_merged_into_request(self):
        pid = self.add_llm("extra-llm", extra='{"tools":[{"type":"web_search_20250305","name":"web_search","max_uses":3}]}')
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        s, _ = call(self.base, "POST", "/api/estimate/food", {"text": "苹果", "date": "2026-09-01"})
        self.assertEqual(s, 200)
        req = next(r for r in self.mock.state.requests if r["kind"] == "llm")
        self.assertEqual(req["body"]["tools"][0]["max_uses"], 3)
        call(self.base, "PUT", "/api/config/task-llm", {})

    def test_bad_llm_output_rejected_with_422(self):
        pid = self.add_llm("bad-llm")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        self.mock.state.bad_json_next = 1
        s, body = call(self.base, "POST", "/api/estimate/food", {"text": "米饭", "date": "2026-09-01"})
        self.assertEqual(s, 422)
        self.assertIn("raw", body["detail"])

    def test_upstream_500_is_502(self):
        pid = self.add_llm("down-llm")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        self.mock.state.fail_next = 1
        s, body = call(self.base, "POST", "/api/estimate/food", {"text": "米饭", "date": "2026-09-01"})
        self.assertEqual(s, 502)
        self.assertIn("HTTP 500", body["error"])

    def test_no_llm_configured(self):
        cfg = Config(self.data / "empty.json")
        eng = Engine(Store(":memory:"), cfg)
        from backend.engine import ApiError
        with self.assertRaises(ApiError) as ctx:
            eng.estimate_food("米饭", date(2026, 9, 1), None)
        self.assertEqual(ctx.exception.status, 400)

    # ---------------- 食物图片识别 ----------------
    # 1x1 PNG
    TINY_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="

    def test_food_image_openai_multimodal(self):
        pid = self.add_llm("vision-openai")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        s, body = call(self.base, "POST", "/api/estimate/food", {
            "text": "这是我的早餐", "date": "2026-09-10", "meal": "早餐",
            "images": [f"data:image/png;base64,{self.TINY_PNG}"]})
        self.assertEqual(s, 200, body)
        self.assertEqual(body["items"][0]["name"], "米饭")
        req = [r for r in self.mock.state.requests if r["kind"] == "llm"][-1]
        self.assertEqual(req["images"], 1)
        content = req["body"]["messages"][1]["content"]
        img = next(p for p in content if p["type"] == "image_url")
        self.assertTrue(img["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertTrue(any(p.get("type") == "text" and "这是我的早餐" in p["text"] for p in content))

    def test_food_image_anthropic_multimodal(self):
        pid = self.add_llm("vision-anthropic", protocol="anthropic", model="claude-vision",
                           base=self.mock.base, key="ant-vision-0001")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        self.mock.state.requests.clear()
        s, body = call(self.base, "POST", "/api/estimate/food", {
            "text": "", "date": "2026-09-10",
            "images": [{"mime": "image/png", "data": self.TINY_PNG}]})
        self.assertEqual(s, 200, body)
        req = next(r for r in self.mock.state.requests if r["kind"] == "llm")
        self.assertEqual(req["images"], 1)
        blocks = req["body"]["messages"][0]["content"]
        self.assertEqual(blocks[0]["type"], "image")
        self.assertEqual(blocks[0]["source"], {"type": "base64", "media_type": "image/png", "data": self.TINY_PNG})
        self.assertEqual(blocks[-1]["type"], "text")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")

    def test_food_image_validation(self):
        pid = self.add_llm("vision-check")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        cases = [
            ({"text": "x", "images": "not-a-list"}, "必须是数组"),
            ({"text": "x", "images": [f"data:image/bmp;base64,{self.TINY_PNG}"]}, "格式不支持"),
            ({"text": "x", "images": ["data:image/png;base64,!!!notbase64"]}, "不是合法 base64"),
            ({"text": "x", "images": [f"data:image/png;base64,{self.TINY_PNG}"] * 5}, "最多上传 4 张"),
            ({"text": "", "images": []}, "请输入饮食描述或上传食物图片"),
        ]
        for payload, expect in cases:
            payload = {"date": "2026-09-10", **payload}
            s, body = call(self.base, "POST", "/api/estimate/food", payload)
            self.assertEqual(s, 400, (payload, body))
            self.assertIn(expect, body["error"])

    def test_food_image_oversize_rejected(self):
        import base64
        big = base64.b64encode(b"\x00" * (5 * 1024 * 1024 + 1)).decode("ascii")
        s, body = call(self.base, "POST", "/api/estimate/food", {
            "text": "x", "date": "2026-09-10", "images": [f"data:image/png;base64,{big}"]})
        self.assertEqual(s, 400)
        self.assertIn("超过 5 MB", body["error"])

    def test_text_only_food_still_works(self):
        # 不带 images 字段时行为与之前完全一致，且请求不含图片
        pid = self.add_llm("text-only")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        self.mock.state.requests.clear()
        s, body = call(self.base, "POST", "/api/estimate/food", {"text": "米饭", "date": "2026-09-10"})
        self.assertEqual(s, 200, body)
        req = next(r for r in self.mock.state.requests if r["kind"] == "llm")
        self.assertIsInstance(req["body"]["messages"][1]["content"], str)
        self.assertNotIn("images", req)
    # ---------------- 记录与每日 ----------------
    def _save_drafts(self, day="2026-09-02"):
        pid = self.add_llm("rec-llm")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        s, est = call(self.base, "POST", "/api/estimate/food", {"text": "米饭、鸡蛋", "date": day, "meal": "午餐"})
        self.assertEqual(s, 200)
        s, act = call(self.base, "POST", "/api/estimate/activity", {"text": "快走40分钟", "date": day})
        self.assertEqual(s, 200)
        items = est["items"] + act["items"]
        s, body = call(self.base, "POST", "/api/entries", {"date": day, "items": items})
        self.assertEqual(s, 201, body)
        return body["entries"]

    def test_save_and_day_balance(self):
        s, _ = call(self.base, "PUT", "/api/profile", {
            "effective_date": "2026-09-01", "sex": "male", "age": 30, "height_cm": 170,
            "weight_kg": 70, "maintenance_kcal": 2000, "bmr_kcal": 1600})
        self.assertEqual(s, 200)
        saved = self._save_drafts("2026-09-02")
        self.assertEqual(len(saved), 3)
        s, day = call(self.base, "GET", "/api/days/2026-09-02")
        self.assertEqual(s, 200)
        food_kcal = 174 + 144
        self.assertAlmostEqual(day["intake"], food_kcal, places=1)
        self.assertAlmostEqual(day["exercise"], 120, places=1)
        self.assertAlmostEqual(day["burn"], 2000 + 120, places=1)
        self.assertAlmostEqual(day["balance"], round(food_kcal - 2120, 1), places=1)
        self.assertEqual(len(day["entries"]), 3)

    def test_user_edit_recomputes_balance(self):
        self._save_drafts("2026-09-03")
        s, day = call(self.base, "GET", "/api/days/2026-09-03")
        food = next(e for e in day["entries"] if e["kind"] == "food")
        s, body = call(self.base, "PUT", f"/api/entries/{food['id']}", {"kcal": 500})
        self.assertEqual(s, 200)
        s, day2 = call(self.base, "GET", "/api/days/2026-09-03")
        self.assertAlmostEqual(day2["intake"], 500 + 144, places=1)
        self.assertAlmostEqual(day2["balance"], round(day2["intake"] - day2["burn"], 1), places=1)

    def test_delete_entry(self):
        saved = self._save_drafts("2026-09-04")
        s, _ = call(self.base, "DELETE", f"/api/entries/{saved[0]['id']}")
        self.assertEqual(s, 200)
        s, day = call(self.base, "GET", "/api/days/2026-09-04")
        self.assertEqual(len(day["entries"]), 2)
        s, _ = call(self.base, "DELETE", f"/api/entries/{saved[0]['id']}")
        self.assertEqual(s, 404)

    def test_manual_save_validation(self):
        s, body = call(self.base, "POST", "/api/entries", {"date": "2026-09-05", "items": [
            {"kind": "food", "name": "", "kcal": 10}]})
        self.assertEqual(s, 400)
        s, body = call(self.base, "POST", "/api/entries", {"date": "2026-09-05", "items": [
            {"kind": "food", "name": "x", "kcal": 99999}]})
        self.assertEqual(s, 400)

    # ---------------- 身体数据 ----------------
    def test_profile_versioning_via_api(self):
        # 用 2024 年的独立日期，避免与其它用例写入的 2026 版本互相干扰
        call(self.base, "PUT", "/api/profile", {"effective_date": "2024-03-01", "weight_kg": 80, "maintenance_kcal": 2200})
        call(self.base, "PUT", "/api/profile", {"effective_date": "2024-04-15", "weight_kg": 75})
        s, p1 = call(self.base, "GET", "/api/profile?date=2024-04-10")
        self.assertEqual(p1["profile"]["weight_kg"], 80)
        s, p2 = call(self.base, "GET", "/api/profile?date=2024-04-20")
        self.assertEqual(p2["profile"]["weight_kg"], 75)
        # 新版本不应清掉未修改字段
        self.assertEqual(p2["profile"]["maintenance_kcal"], 2200)
        s, hist = call(self.base, "GET", "/api/profile/history")
        self.assertGreaterEqual(len(hist["history"]), 2)

    def test_profile_validation(self):
        s, _ = call(self.base, "PUT", "/api/profile", {"weight_kg": 0})
        self.assertEqual(s, 400)
        s, _ = call(self.base, "PUT", "/api/profile", {"sex": "robot"})
        self.assertEqual(s, 400)
        s, _ = call(self.base, "PUT", "/api/profile", {"bogus": 1})
        self.assertEqual(s, 400)
        s, _ = call(self.base, "PUT", "/api/profile", {"bmr_kcal": 2000, "maintenance_kcal": 1500})
        self.assertEqual(s, 400)

    def test_ai_estimate_metabolism(self):
        pid = self.add_llm("meta-llm")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        call(self.base, "PUT", "/api/config/task-llm", {"metabolism_estimate": pid})
        call(self.base, "PUT", "/api/profile", {"effective_date": "2026-09-01", "weight_kg": 70, "height_cm": 170, "age": 30})
        s, body = call(self.base, "POST", "/api/profile/estimate-metabolism", {"date": "2026-09-01"})
        self.assertEqual(s, 200, body)
        self.assertEqual(body["bmr_kcal"], 1600)
        self.assertEqual(body["maintenance_kcal"], 2080)
        call(self.base, "PUT", "/api/config/task-llm", {})

    # ---------------- 报告 ----------------
    def test_weekly_report_with_analysis(self):
        s, _ = call(self.base, "PUT", "/api/profile", {"effective_date": "2026-09-01", "maintenance_kcal": 2000, "weight_kg": 70})
        self._save_drafts("2026-09-07")
        pid = self.add_llm("report-llm")
        call(self.base, "POST", f"/api/config/llm/{pid}/activate")
        s, rep = call(self.base, "POST", "/api/reports", {"period": "week", "date": "2026-09-09", "analyze": True})
        self.assertEqual(s, 200, rep)
        self.assertEqual(rep["start"], "2026-09-07")
        self.assertEqual(rep["end"], "2026-09-13")
        self.assertEqual(rep["stats"]["days_logged"], 1)
        self.assertEqual(rep["analysis"]["diet_score"], 70)
        self.assertEqual(rep["analysis"]["exercise_level"], "规律")
        # 分析请求中应包含统计 JSON
        req = [r for r in self.mock.state.requests if r["kind"] == "llm"][-1]
        self.assertIn("统计数据", req["body"]["messages"][1]["content"])
        s, saved = call(self.base, "GET", f"/api/reports/{rep['id']}")
        self.assertEqual(s, 200)
        self.assertEqual(saved["analysis"]["summary"], rep["analysis"]["summary"])
        s, lst = call(self.base, "GET", "/api/reports")
        self.assertTrue(any(r["id"] == rep["id"] for r in lst["reports"]))

    def test_monthly_report_without_analysis(self):
        self.mock.state.requests.clear()
        s, rep = call(self.base, "POST", "/api/reports", {"period": "month", "date": "2026-09-15", "analyze": False})
        self.assertEqual(s, 200, rep)
        self.assertEqual(rep["start"], "2026-09-01")
        self.assertEqual(rep["end"], "2026-09-30")
        self.assertEqual(rep["stats"]["days_total"], 30)
        self.assertIsNone(rep["analysis"])
        self.assertFalse([r for r in self.mock.state.requests if r["kind"] == "llm"])

    def test_report_for_empty_period_skips_ai(self):
        s, rep = call(self.base, "POST", "/api/reports", {"period": "week", "date": "2025-01-06", "analyze": True})
        self.assertEqual(s, 200)
        self.assertIsNone(rep["analysis"])
        self.assertTrue(rep["warnings"])

    def test_bad_report_period(self):
        s, _ = call(self.base, "POST", "/api/reports", {"period": "year", "date": "2026-09-01"})
        self.assertEqual(s, 400)

    # ---------------- 静态页面与安全 ----------------
    def test_frontend_served(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as resp:
            html = resp.read().decode("utf-8")
        self.assertIn("热量管理", html)
        with urllib.request.urlopen(self.base + "/app.js", timeout=10) as resp:
            self.assertIn("async function api", resp.read().decode("utf-8"))

    def test_i18n_js_served(self):
        # 国际化字典必须可被静态服务，且包含两种语言代码
        with urllib.request.urlopen(self.base + "/i18n.js", timeout=10) as resp:
            self.assertEqual(resp.status, 200)
            js = resp.read().decode("utf-8")
        self.assertIn("zh-CN", js)
        self.assertIn('"en"', js)

    def test_index_has_i18n_hooks_and_title(self):
        # 首页应包含 data-i18n 标记，且默认文字与 <title> 仍为「热量管理」
        with urllib.request.urlopen(self.base + "/", timeout=10) as resp:
            html = resp.read().decode("utf-8")
        self.assertIn("data-i18n", html)
        self.assertIn("<title", html)
        self.assertIn("热量管理", html)
        index_src = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn("热量管理", index_src)

    def test_i18n_dict_keys_match(self):
        # zh-CN 与 en 两个字典的 key 必须完全一致（按行解析 "key": "value" 形式）
        import re
        src = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")
        zh_block = src.split('"zh-CN": {', 1)[1].split('"en": {', 1)[0]
        en_block = src.split('"en": {', 1)[1]
        key_re = re.compile(r'^\s*"([^"]+)":\s*"', re.M)
        zh_keys = set(key_re.findall(zh_block))
        en_keys = set(key_re.findall(en_block))
        self.assertTrue(zh_keys)
        self.assertEqual(zh_keys, en_keys)

    # ---------------- 前端结构契约（0.3.0 界面重做后固化，防止改 UI 误伤功能） ----------------
    @staticmethod
    def _front(name):
        return (ROOT / "frontend" / name).read_text(encoding="utf-8")

    def test_frontend_ids_used_by_js_exist_in_html(self):
        import re
        html, js = self._front("index.html"), self._front("app.js")
        html_ids = set(re.findall(r'\bid="([^"]+)"', html))
        used = set(re.findall(r'\$\(\s*"#([\w-]+)"', js)) | set(re.findall(r'setBox\(\s*"#([\w-]+)"', js)) \
            | set(re.findall(r'setStatus\(\s*"#([\w-]+)"', js))
        self.assertTrue(used)
        self.assertEqual(sorted(used - html_ids), [], "app.js 引用了 index.html 中不存在的 id")

    def test_frontend_tabs_and_forms_intact(self):
        import re
        html = self._front("index.html")
        tabs = re.findall(r'data-tab="(\w+)"', html)
        self.assertEqual(tabs, ["record", "day", "report", "profile", "settings"])
        for tab in tabs:
            self.assertIn(f'id="tab-{tab}"', html)
        for name in ("sex", "age", "height_cm", "weight_kg", "activity_text", "goal_text", "bmr_kcal",
                     "maintenance_kcal", "effective_date"):
            self.assertIn(f'name="{name}"', html, f"身体数据表单缺少 {name}")
        for name in ("id", "name", "protocol", "model", "base_url", "api_key", "temperature", "max_tokens",
                     "json_mode", "extra_body"):
            self.assertIn(f'name="{name}"', html, f"LLM 表单缺少 {name}")
        for sel in ("apiBase", "btnChangelog", "changelogModal", "foodImages", "btnEstFood", "btnEstAct"):
            self.assertIn(f'id="{sel}"', html)

    def test_frontend_action_hooks_preserved(self):
        js = self._front("app.js")
        for hook in ("data-save=", "data-remove=", "data-del=", "data-edit=", "data-test=", "data-activate=",
                     "data-delete=", "data-report=", "data-rm-img=", "data-save-prompt=", "data-reset-prompt=",
                     "data-task="):
            self.assertIn(hook, js, f"app.js 丢失事件钩子 {hook}")
        # 事件委托必须用 closest，点到按钮内部元素也能触发
        self.assertIn('closest("[data-save],[data-remove]")', js)
        self.assertIn('closest("[data-del]")', js)

    def test_frontend_hidden_attribute_and_theme_support(self):
        css = self._front("style.css")
        self.assertIn("[hidden] { display: none !important; }", css)
        for theme in ("ocean", "plum"):
            self.assertIn(f':root[data-theme="{theme}"]', css)
        html = self._front("index.html")
        for theme in ("forest", "ocean", "plum"):
            self.assertIn(f'data-theme="{theme}"', html)
        # 窄屏顶栏不能带 backdrop-filter，否则内部 position:fixed 的底栏会错位
        narrow = css.split("@media (max-width: 780px)", 1)[1].split("}", 1)[0]
        self.assertIn("backdrop-filter: none", narrow)

    def test_changelog_has_030_in_history_zh_and_en(self):
        import json as _json
        data = _json.loads(self._front("changelog.json"))
        self.assertEqual(data["version"], "0.3.1")
        self.assertEqual(data["history"][0]["version"], "0.3.1")
        for h in data["history"]:
            self.assertTrue(h["items"] and h["items_en"], f"v{h['version']} 缺少中文或英文条目")
        self.assertEqual(len(data["history"][0]["items"]), len(data["history"][0]["items_en"]))
        self.assertEqual([h["version"] for h in data["history"]][:4], ["0.3.1", "0.3.0", "0.2.1", "0.2.0"])

    def test_i18n_keys_used_in_js_and_html_exist(self):
        import re
        src = self._front("i18n.js")
        zh_block = src.split('"zh-CN": {', 1)[1].split('"en": {', 1)[0]
        keys = set(re.findall(r'^\s*"([^"]+)":\s*"', zh_block, re.M))
        # 只校验完整字面量键 t("a.b")/t("a.b", {...})；t("task." + id) 这类动态拼接不在此列
        used = set(re.findall(r'\bt\(\s*"([\w.]+)"\s*[,)]', self._front("app.js")))
        used |= set(re.findall(r'data-i18n(?:-html|-placeholder|-title)?="([\w.]+)"', self._front("index.html")))
        self.assertEqual(sorted(k for k in used if k not in keys), [], "代码或页面引用了字典中不存在的文案键")

    def test_static_path_traversal_blocked(self):
        try:
            with urllib.request.urlopen(self.base + "/..%2Fbackend%2Fconfig.py", timeout=10) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status, body = exc.code, ""
        self.assertEqual(status, 404)
        self.assertNotIn("class Config", body)

    # ---------------- 合规：同意文档 ----------------
    def test_privacy_and_terms_pages_served_bilingual(self):
        """隐私政策与用户协议必须是可访问的静态页，且中英文内容都在同一个文件里。"""
        for path, must_have in (("/privacy.html", ("隐私政策", "Privacy Policy")),
                                ("/terms.html", ("用户协议", "User Agreement"))):
            with urllib.request.urlopen(self.base + path, timeout=10) as resp:
                self.assertEqual(resp.status, 200, path)
                html = resp.read().decode("utf-8")
            for text in must_have:
                self.assertIn(text, html, f"{path} 缺少 {text}")
            # 两个语言块都要在，切换按钮才有效
            self.assertIn('data-lang-block="zh-CN"', html)
            self.assertIn('data-lang-block="en"', html)

    def test_privacy_policy_covers_mandatory_topics(self):
        """合规必备章节：数据种类、存储、第三方共享/出境、权限、用户权利、未成年人、联系方式。"""
        html = (ROOT / "frontend" / "privacy.html").read_text(encoding="utf-8")
        for topic in ("不收集", "API Key", "第三方", "出境", "权限", "导出", "删除",
                      "未成年人", "联系", "ACCESS_NETWORK_STATE"):
            self.assertIn(topic, html, f"隐私政策缺少必备内容：{topic}")

    def test_terms_disclaims_medical_advice(self):
        html = (ROOT / "frontend" / "terms.html").read_text(encoding="utf-8")
        self.assertIn("不是医疗器械", html)
        self.assertIn("不构成医疗建议", html)
        self.assertIn("责任限制", html)
        # 英文侧同样要有免责
        self.assertIn("not a medical device", html)
        self.assertIn("do not constitute medical advice", html)

    def test_consent_gate_blocks_network_until_agreed(self):
        """同意层必须先于任何网络请求：未同意时 init 只打开同意层，联网动作全部在 startApp 里。"""
        js = self._front("app.js")
        for needle in ("CONSENT_KEY", "POLICY_VERSION", "function hasConsented()",
                       "function openConsentGate()", "function startApp()"):
            self.assertIn(needle, js)
        init_body = js.split("\nfunction init()", 1)[1].split("\n/* 取得同意后才执行", 1)[0]
        # init 的收尾必须是「未同意 → 只开同意层；已同意 → startApp」的二选一
        tail = init_body.rsplit("if (!hasConsented())", 1)[1]
        self.assertIn("openConsentGate();", tail)
        self.assertIn("} else {", tail, "未同意时不得落到 startApp 分支")
        self.assertIn("startApp();", tail)
        # 未同意分支内部不能有联网调用
        branch = tail.split("} else {", 1)[0]
        for net in ("startApp()", "checkHealth()", "loadDay()", "loadProfile()", "maybeShowChangelog"):
            self.assertNotIn(net, branch, f"未同意分支里不得调用 {net}")
        # 首次联网只能由 startApp 触发
        start_body = js.split("\nfunction startApp()", 1)[1].split("\ndocument.addEventListener", 1)[0]
        self.assertIn("checkHealth()", start_body)
        self.assertIn("maybeShowChangelog", start_body)
        # 同意按钮的回调负责在同意后启动
        agree = js.split('$("#consentAgree").addEventListener("click"', 1)[1].split("});", 1)[0]
        self.assertIn("saveConsent();", agree)
        self.assertIn("startApp();", agree)

    def test_consent_ui_ids_match_between_html_and_js(self):
        import re
        html, js = self._front("index.html"), self._front("app.js")
        html_ids = set(re.findall(r'\bid="([^"]+)"', html))
        for el in ("consentGate", "consentAgree", "consentDecline", "consentRetry",
                   "consentPrivacy", "consentTerms", "consentAsk", "consentDeclined",
                   "btnExportData", "btnClearData", "btnWithdrawConsent", "dataResult"):
            self.assertIn(el, html_ids, f"index.html 缺少同意/数据管理元素 {el}")
            self.assertIn(f'"#{el}"', js, f"app.js 未绑定 {el}")

    def test_app_discloses_ai_content_and_medical_disclaimer(self):
        js = self._front("app.js")
        self.assertIn('t("ai.badge")', js)
        self.assertIn('t("ai.disclaimer")', js)
        self.assertIn('t("legal.footerDisclaimer")', js)
        html = self._front("index.html")
        self.assertIn('data-i18n="ai.badge"', html)


class DataRightsAndLocalAccess(unittest.TestCase):
    """数据导出/删除（用户权利）与本地服务访问控制。"""

    @classmethod
    def setUpClass(cls):
        cls.data = ROOT / "tests" / ".data" / f"compliance-{threading.get_ident()}"
        cls.data.mkdir(parents=True, exist_ok=True)
        cls.engine = Engine(Store(cls.data / "ct.db"), Config(cls.data / "config.json"))
        # 带口令启动：安卓端就是这种模式
        cls.token = "unit-test-token-0123456789"
        cls.httpd = make_server(cls.engine, "127.0.0.1", 0, token=cls.token)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.engine.store.close()

    def setUp(self):
        # 每个用例从干净状态开始
        call_tok(self.base, self.token, "POST", "/api/data/clear", {})

    # --- helpers
    def seed(self):
        s, _ = call_tok(self.base, self.token, "PUT", "/api/profile", {
            "effective_date": "2025-01-01", "sex": "female", "age": 30,
            "height_cm": 165, "weight_kg": 55, "activity_text": "久坐",
            "goal_text": "减脂", "bmr_kcal": 1300, "maintenance_kcal": 1800,
        })
        self.assertEqual(s, 200)
        s, body = call_tok(self.base, self.token, "POST", "/api/entries", {
            "date": "2025-01-02",
            "items": [{"kind": "food", "name": "米饭", "grams": 200, "kcal": 232, "meal": "午餐"},
                      {"kind": "activity", "name": "快走", "minutes": 40, "kcal": 150}],
        })
        self.assertEqual(s, 201, body)

    # --- 访问控制
    def test_api_rejects_missing_or_wrong_token(self):
        for headers in ({}, {"X-CT-Token": "wrong-token"}):
            s, body = call(self.base, "GET", "/api/profile", headers=headers)
            self.assertEqual(s, 403, body)
            self.assertIn("口令", body["error"])

    def test_api_accepts_correct_token(self):
        s, body = call_tok(self.base, self.token, "GET", "/api/health")
        self.assertEqual(s, 200)
        self.assertTrue(body["ok"])

    def test_static_pages_need_no_token(self):
        """静态资源不校验口令，否则 WebView 加载页面本身就会失败。"""
        for path in ("/", "/app.js", "/privacy.html", "/terms.html", "/style.css"):
            with urllib.request.urlopen(self.base + path, timeout=10) as resp:
                self.assertEqual(resp.status, 200, path)

    def test_non_loopback_host_header_rejected(self):
        """DNS rebinding 防护：Host 不是回环地址时拒绝。"""
        s, body = call(self.base, "GET", "/api/health", headers={"Host": "evil.example.com"})
        self.assertEqual(s, 403, body)
        self.assertIn("本机", body["error"])

    def test_cors_not_wildcard(self):
        """跨源头不得使用通配符，只对回环来源回显。"""
        import urllib.request as _u
        req = _u.Request(self.base + "/api/health", method="GET",
                         headers={"X-CT-Token": self.token, "Origin": "https://evil.example.com"})
        with _u.urlopen(req, timeout=10) as resp:
            self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))
            self.assertEqual(resp.headers.get("Referrer-Policy"), "no-referrer")
            self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        req2 = _u.Request(self.base + "/api/health", method="GET",
                          headers={"X-CT-Token": self.token, "Origin": "http://127.0.0.1:8787"})
        with _u.urlopen(req2, timeout=10) as resp:
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://127.0.0.1:8787")

    # --- 数据导出
    def test_export_contains_all_data_without_api_key_secrets(self):
        self.seed()
        call_tok(self.base, self.token, "POST", "/api/config/llm", {
            "name": "secret-profile", "protocol": "openai", "model": "m",
            "base_url": "https://api.example.com/v1", "api_key": "sk-super-secret-9876",
        })
        s, dump = call_tok(self.base, self.token, "GET", "/api/data/export")
        self.assertEqual(s, 200)
        self.assertEqual(dump["app"], "calorie-tracker")
        self.assertEqual(dump["version"], "0.3.1")
        self.assertTrue(dump["exported_at"])
        # 全量数据
        self.assertEqual(len(dump["entries"]), 2)
        self.assertEqual(len(dump["profiles"]), 1)
        self.assertEqual(dump["profiles"][0]["data"]["weight_kg"], 55)
        # 配置在，但密钥不泄露
        raw = json.dumps(dump, ensure_ascii=False)
        self.assertNotIn("sk-super-secret-9876", raw)
        self.assertIn("api_key_set", raw)
        self.assertEqual(dump["config"]["llm_profiles"][0]["api_key_hint"], "…9876")

    def test_export_is_valid_json_and_empty_safe(self):
        call_tok(self.base, self.token, "POST", "/api/data/clear", {})
        s, dump = call_tok(self.base, self.token, "GET", "/api/data/export")
        self.assertEqual(s, 200)
        self.assertEqual(dump["entries"], [])
        self.assertEqual(dump["profiles"], [])
        self.assertEqual(dump["reports"], [])

    # --- 数据删除
    def test_clear_removes_everything(self):
        self.seed()
        call_tok(self.base, self.token, "POST", "/api/reports",
                 {"period": "week", "date": "2025-01-02", "analyze": False})
        s, body = call_tok(self.base, self.token, "POST", "/api/data/clear", {})
        self.assertEqual(s, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["removed"], {"profiles": 1, "entries": 2, "reports": 1})
        # 清空后各接口都应返回空
        s, entries = call_tok(self.base, self.token, "GET", "/api/entries?date=2025-01-02")
        self.assertEqual(entries["entries"], [])
        s, profile = call_tok(self.base, self.token, "GET", "/api/profile?date=2025-01-02")
        self.assertEqual(profile["profile"], {})
        s, reports = call_tok(self.base, self.token, "GET", "/api/reports")
        self.assertEqual(reports["reports"], [])
        # 再次清除是幂等的
        s, body = call_tok(self.base, self.token, "POST", "/api/data/clear", {})
        self.assertEqual(body["removed"], {"profiles": 0, "entries": 0, "reports": 0})

    def test_reports_can_be_deleted(self):
        self.seed()
        s, rep = call_tok(self.base, self.token, "POST", "/api/reports",
                          {"period": "week", "date": "2025-01-02", "analyze": False})
        self.assertEqual(s, 200)
        rid = rep["id"]
        s, _ = call_tok(self.base, self.token, "DELETE", f"/api/reports/{rid}")
        self.assertEqual(s, 200)
        s, body = call_tok(self.base, self.token, "GET", f"/api/reports/{rid}")
        self.assertEqual(s, 404, body)


if __name__ == "__main__":
    unittest.main()
