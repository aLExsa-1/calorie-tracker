"""UI 演示服务：独立临时数据目录 + 模拟 LLM，预填演示数据，仅用于界面截图自检。

不读取 data/（含真实 API Key）；演示用的 Key 是假的。
用法（前台运行，结束进程即退出）：
    python tests/tools/ui_demo.py [--port 8799] [--empty]
--empty：不预填数据，用于检查首次使用的空状态。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from backend.config import Config  # noqa: E402
from backend.engine import Engine  # noqa: E402
from backend.server import make_server  # noqa: E402
from backend.store import Store  # noqa: E402
from mock_llm import MockServer  # noqa: E402


def call(base, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def food(meal, name, grams, kcal, p, c, f, conf="high"):
    return {"kind": "food", "meal": meal, "name": name, "grams": grams, "kcal": kcal, "protein_g": p,
            "carb_g": c, "fat_g": f, "confidence": conf, "basis": "演示数据", "llm_name": "演示模型"}


def act(name, minutes, kcal):
    return {"kind": "activity", "name": name, "minutes": minutes, "kcal": kcal,
            "basis": "演示数据", "llm_name": "演示模型"}


def seed(base, mock_base):
    d = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731

    call(base, "POST", "/api/config/llm", {
        "name": "演示模型", "protocol": "openai", "model": "demo-chat", "base_url": mock_base + "/v1",
        "api_key": "sk-demo-0000abcd", "temperature": 0.2, "max_tokens": 4096, "extra_body": ""})
    call(base, "POST", "/api/config/llm", {
        "name": "演示 Claude", "protocol": "anthropic", "model": "demo-claude", "base_url": mock_base,
        "api_key": "sk-demo-1111wxyz", "temperature": 0.2, "max_tokens": 4096, "extra_body": ""})

    for offset, weight, bmr, maint in ((-40, 66.0, 1580, 2140), (-14, 64.5, 1588, 2165), (0, 63.0, 1594, 2191)):
        call(base, "PUT", "/api/profile", {
            "sex": "male", "age": 22, "height_cm": 171, "weight_kg": weight,
            "activity_text": "每天步数 6000 步，办公室久坐", "goal_text": "自由减脂增肌",
            "bmr_kcal": bmr, "maintenance_kcal": maint, "effective_date": d(offset)})

    plans = {
        0: [food("早餐", "燕麦牛奶粥", 350, 286, 11.2, 42.5, 7.8), food("早餐", "水煮蛋", 100, 144, 12.6, 1.5, 9.5),
            food("午餐", "鸡胸肉沙拉", 320, 358, 38.4, 14.2, 15.6), food("午餐", "米饭", 150, 174, 3.9, 38.9, 0.5),
            food("晚餐", "清蒸鲈鱼", 200, 188, 36.2, 0.8, 4.6), food("晚餐", "炒青菜", 180, 92, 3.1, 9.6, 4.8),
            food("加餐", "苹果", 200, 104, 0.6, 27.6, 0.4, "medium"),
            act("快走", 40, 120), act("力量训练", 45, 210)],
        -1: [food("早餐", "煎饼果子", 280, 520, 14.0, 62.0, 22.0), food("午餐", "红烧肉盖饭", 520, 980, 32.0, 110.0, 44.0, "medium"),
             food("晚餐", "火锅（牛肉、蔬菜、蘸料）", 900, 1400, 62.0, 58.0, 96.0, "low"), food("加餐", "奶茶", 500, 450, 4.0, 72.0, 15.0)],
        -3: [food("早餐", "全麦面包", 90, 230, 9.0, 42.0, 3.0), food("午餐", "牛肉面", 600, 620, 28.0, 90.0, 16.0),
             food("晚餐", "番茄炒蛋", 250, 280, 14.0, 12.0, 20.0), act("慢跑", 30, 260)],
        -4: [food("早餐", "豆浆油条", 300, 420, 12.0, 48.0, 20.0), food("午餐", "盖浇饭", 480, 760, 26.0, 98.0, 28.0),
             food("晚餐", "蔬菜汤面", 450, 410, 14.0, 66.0, 9.0)],
        -5: [food("午餐", "鸡腿饭", 500, 820, 38.0, 96.0, 30.0), food("晚餐", "酸奶水果杯", 260, 230, 8.0, 36.0, 6.0),
             act("骑行", 50, 300)],
        -6: [food("早餐", "三明治", 200, 380, 16.0, 40.0, 17.0), food("晚餐", "饺子", 300, 520, 20.0, 64.0, 18.0)],
    }
    for offset, items in plans.items():
        call(base, "POST", "/api/entries", {"date": d(offset), "items": items})

    call(base, "POST", "/api/reports", {"period": "week", "date": d(-1), "analyze": True})
    call(base, "POST", "/api/reports", {"period": "month", "date": d(0), "analyze": True})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--empty", action="store_true")
    args = ap.parse_args()

    data = ROOT / "tests" / ".data" / ("ui-demo-empty" if args.empty else "ui-demo")
    if data.exists():
        shutil.rmtree(data)
    data.mkdir(parents=True)

    mock = MockServer().start()
    engine = Engine(Store(data / "ct.db"), Config(data / "config.json"))
    httpd = make_server(engine, "127.0.0.1", args.port)
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{args.port}"
    if not args.empty:
        seed(base, mock.base)
    print(f"UI 演示服务就绪：{base}（数据：{data}，{'空库' if args.empty else '已预填'}）", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        mock.stop()


if __name__ == "__main__":
    main()
