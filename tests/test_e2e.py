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


def call(base, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


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

    def test_health_version_is_0_2_0(self):
        s, body = call(self.base, "GET", "/api/health")
        self.assertEqual(s, 200)
        self.assertEqual(body["version"], "0.2.1")

    def test_changelog_json_served(self):
        import json as _json
        import urllib.request
        with urllib.request.urlopen(self.base + "/changelog.json", timeout=5) as r:
            data = _json.loads(r.read().decode("utf-8"))
        self.assertEqual(data["version"], "0.2.1")
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

    def test_static_path_traversal_blocked(self):
        try:
            with urllib.request.urlopen(self.base + "/..%2Fbackend%2Fconfig.py", timeout=10) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status, body = exc.code, ""
        self.assertEqual(status, 404)
        self.assertNotIn("class Config", body)


if __name__ == "__main__":
    unittest.main()
