"""业务规则框架。

本模块不包含任何食物库、MET 表或代谢公式：这些都由配置的 LLM 完成。
这里只负责：
- 组装提示词变量、调用搜索与 LLM、校验输出结构；
- 身体数据的版本管理与合法范围检查；
- 记录的增删改（金额为 AI 估算或用户修改后的值）；
- 日热量差 = 摄入 − (维持消耗 + 运动消耗) 的算术；
- 周/月统计汇总，并交给 LLM 做分析。
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

from . import schemas
from .config import Config, ConfigError
from .llm import LLMError, call_llm, parse_json
from .llm import list_models as llm_list_models
from .prompts import OUTPUT_FORMAT, SEARCH_BLOCK, TASKS
from .search import SearchError, format_results, search
from .store import Store

PROFILE_FIELDS = ("sex", "age", "height_cm", "weight_kg", "activity_text", "goal_text",
                  "bmr_kcal", "maintenance_kcal", "extra")
PROFILE_RANGES = {
    "age": (1, 120), "height_cm": (50, 260), "weight_kg": (2, 400),
    "bmr_kcal": (300, 5000), "maintenance_kcal": (500, 8000),
}
SEXES = ("male", "female", "other", "")

# 自定义条目库字段取值范围（与记录 entries 的口径一致）
FOOD_RANGES = {"kcal": (0, 5000), "grams": (0, 10000),
               "protein_g": (0, 1000), "carb_g": (0, 1000), "fat_g": (0, 1000)}
ACTIVITY_RANGES = {"kcal": (0, 5000), "minutes": (0, 1440)}


class ApiError(Exception):
    def __init__(self, status: int, message: str, detail=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.detail = detail


def render(template: str, variables: dict) -> str:
    out = template
    for k, v in variables.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


class Engine:
    def __init__(self, store: Store, config: Config):
        self.store = store
        self.config = config

    # ================= AI 任务执行 =================
    def run_task(self, task: str, variables: dict, images: list | None = None) -> tuple[dict, dict]:
        prompt = self.config.prompt(task)
        try:
            profile = self.config.resolve_llm(task)
        except ConfigError as exc:
            raise ApiError(400, str(exc))

        warnings: list[str] = []
        search_block = ""
        search_cfg = self.config.search_full()
        if prompt["use_search"] and search_cfg["provider"] != "none" and prompt["search_query"]:
            query = render(prompt["search_query"], variables)
            try:
                rows = search(search_cfg, query)
                if rows:
                    search_block = SEARCH_BLOCK.replace("{results}", format_results(rows))
            except SearchError as exc:
                warnings.append(f"联网搜索失败，已跳过：{exc}")

        user = render(prompt["user"], {**variables, "search": search_block})
        system = prompt["system"] + "\n\n输出要求：只输出一个 JSON 对象，不要输出其它文字。结构如下：\n" + OUTPUT_FORMAT[task]
        try:
            text = call_llm(profile, system, user, images=images)
        except LLMError as exc:
            raise ApiError(502, f"LLM 调用失败：{exc}")
        try:
            data = parse_json(text)
            result = schemas.validate(task, data)
        except (LLMError, schemas.SchemaError) as exc:
            # 输出无法解析或不符合规则：422，并附上原始输出便于排查
            raise ApiError(422, f"LLM 输出不符合规则：{exc}", detail={"raw": text[:1500]})

        meta = {"llm": profile["name"], "model": profile["model"],
                "search_used": bool(search_block), "warnings": warnings, "images": len(images or [])}
        return result, meta

    # ================= 身体数据 =================
    def profile_on(self, day: date) -> dict:
        return self.store.profile_on(day.isoformat())

    def update_profile(self, body: dict) -> dict:
        effective = body.pop("effective_date", None) or date.today().isoformat()
        try:
            effective_day = date.fromisoformat(effective)
        except ValueError:
            raise ApiError(400, "effective_date 格式应为 YYYY-MM-DD")
        unknown = set(body) - set(PROFILE_FIELDS)
        if unknown:
            raise ApiError(400, f"未知字段：{', '.join(sorted(unknown))}")

        merged = {k: v for k, v in self.profile_on(effective_day).items() if k != "effective_date"}
        merged.update(body)
        if merged.get("sex", "") not in SEXES:
            raise ApiError(400, "sex 只能是 male / female / other 或留空")
        for field, (lo, hi) in PROFILE_RANGES.items():
            value = merged.get(field)
            if value in (None, ""):
                merged[field] = None
                continue
            try:
                x = float(value)
            except (TypeError, ValueError):
                raise ApiError(400, f"{field} 必须是数字")
            if not lo <= x <= hi:
                raise ApiError(400, f"{field} 应在 {lo}–{hi} 之间")
            merged[field] = round(x, 2)
        if merged.get("bmr_kcal") and merged.get("maintenance_kcal") \
                and merged["maintenance_kcal"] < merged["bmr_kcal"]:
            raise ApiError(400, "维持消耗不应低于基础代谢")
        if not isinstance(merged.get("extra") or {}, dict):
            raise ApiError(400, "extra 必须是 JSON 对象")
        merged["extra"] = merged.get("extra") or {}
        self.store.add_profile_version(effective_day.isoformat(), merged)
        return self.profile_on(effective_day)

    def estimate_metabolism(self, day: date) -> dict:
        profile = self.profile_on(day)
        result, meta = self.run_task("metabolism_estimate", {
            "profile": json.dumps(profile, ensure_ascii=False),
            "input": "",
        })
        return {**result, **meta}

    # ================= AI 估算（草稿，不写库） =================
    def estimate_food(self, text: str, day: date, meal: str | None, images: list | None = None) -> dict:
        text = text.strip()
        if not text and not images:
            raise ApiError(400, "请输入饮食描述或上传食物图片")
        images = images or []
        result, meta = self.run_task("food_estimate", {
            "input": text or "（见图片）",
            "meal": meal or "未指定",
            "profile": json.dumps(self.profile_on(day), ensure_ascii=False),
        }, images=images)
        items = [{**it, "kind": "food", "meal": meal or "", "raw_text": text.strip(),
                  "llm_name": meta["llm"]} for it in result["items"]]
        return {"items": items, "notes": result["notes"], **{k: meta[k] for k in ("llm", "search_used", "warnings")}}

    def estimate_activity(self, text: str, day: date) -> dict:
        if not text.strip():
            raise ApiError(400, "请输入运动描述")
        result, meta = self.run_task("activity_estimate", {
            "input": text.strip(),
            "profile": json.dumps(self.profile_on(day), ensure_ascii=False),
        })
        items = [{**it, "kind": "activity", "meal": "", "raw_text": text.strip(),
                  "llm_name": meta["llm"]} for it in result["items"]]
        return {"items": items, "notes": result["notes"], **{k: meta[k] for k in ("llm", "search_used", "warnings")}}

    # ================= 自定义条目库（不经 AI，用户手工维护） =================
    @staticmethod
    def _lib_num(value, field: str, lo: float, hi: float, required: bool = False):
        if value in (None, ""):
            if required:
                raise ApiError(400, f"{field} 不能为空")
            return None
        try:
            x = float(value)
        except (TypeError, ValueError):
            raise ApiError(400, f"{field} 必须是数字")
        if not lo <= x <= hi:
            raise ApiError(400, f"{field} 应在 {lo:g}–{hi:g} 之间")
        return round(x, 1)

    def library(self) -> dict:
        return {"foods": self.store.list_custom_foods(),
                "activities": self.store.list_custom_activities()}

    def save_custom_food(self, body: dict) -> dict:
        try:
            fid = int(body["id"]) if body.get("id") not in (None, "") else None
        except (TypeError, ValueError):
            raise ApiError(400, "id 必须是整数")
        name = str(body.get("name") or "").strip()
        if not name:
            raise ApiError(400, "名称不能为空")
        fields = {"name": name[:60]}
        for field, (lo, hi) in FOOD_RANGES.items():
            fields[field] = self._lib_num(body.get(field), field, lo, hi,
                                          required=(field == "kcal"))
        fields["serving_label"] = str(body.get("serving_label") or "").strip()[:40] or None
        fields["notes"] = str(body.get("notes") or "").strip()[:500] or None
        rid = self.store.upsert_custom_food(fid, fields)
        if not rid:
            raise ApiError(404, "自定义食物不存在")
        saved = self.store.get_custom_food(rid)
        return saved

    def delete_custom_food(self, fid: int) -> None:
        if not self.store.delete_custom_food(fid):
            raise ApiError(404, "自定义食物不存在")

    def save_custom_activity(self, body: dict) -> dict:
        try:
            aid = int(body["id"]) if body.get("id") not in (None, "") else None
        except (TypeError, ValueError):
            raise ApiError(400, "id 必须是整数")
        name = str(body.get("name") or "").strip()
        if not name:
            raise ApiError(400, "名称不能为空")
        fields = {"name": name[:60]}
        for field, (lo, hi) in ACTIVITY_RANGES.items():
            fields[field] = self._lib_num(body.get(field), field, lo, hi,
                                          required=(field == "kcal"))
        fields["notes"] = str(body.get("notes") or "").strip()[:500] or None
        rid = self.store.upsert_custom_activity(aid, fields)
        if not rid:
            raise ApiError(404, "自定义运动不存在")
        saved = self.store.get_custom_activity(rid)
        return saved

    def delete_custom_activity(self, aid: int) -> None:
        if not self.store.delete_custom_activity(aid):
            raise ApiError(404, "自定义运动不存在")

    # ================= 记录 =================
    def save_entries(self, day: date, items: list[dict]) -> list[dict]:
        if not items:
            raise ApiError(400, "没有可保存的条目")
        rows = []
        for i, it in enumerate(items):
            kind = it.get("kind")
            if kind not in ("food", "activity"):
                raise ApiError(400, f"第 {i + 1} 条：kind 只能是 food 或 activity")
            if not str(it.get("name") or "").strip():
                raise ApiError(400, f"第 {i + 1} 条：名称不能为空")
            try:
                kcal = float(it.get("kcal"))
            except (TypeError, ValueError):
                raise ApiError(400, f"第 {i + 1} 条：热量必须是数字")
            if not 0 <= kcal <= 5000:
                raise ApiError(400, f"第 {i + 1} 条：热量超出 0–5000 范围")
            rows.append({
                "date": day.isoformat(), "meal": it.get("meal") or None, "kind": kind,
                "name": str(it["name"]).strip(), "grams": it.get("grams"), "minutes": it.get("minutes"),
                "kcal": round(kcal, 1), "protein_g": it.get("protein_g"), "carb_g": it.get("carb_g"),
                "fat_g": it.get("fat_g"), "confidence": it.get("confidence"), "basis": it.get("basis"),
                "raw_text": it.get("raw_text"), "llm_name": it.get("llm_name") or "manual",
            })
        ids = self.store.insert_entries(rows)
        return [self._entry_view(self.store.get_entry(i)) for i in ids]

    def update_entry(self, eid: int, fields: dict) -> dict:
        if not self.store.get_entry(eid):
            raise ApiError(404, "记录不存在")
        if "kcal" in fields:
            try:
                kcal = float(fields["kcal"])
            except (TypeError, ValueError):
                raise ApiError(400, "热量必须是数字")
            if not 0 <= kcal <= 5000:
                raise ApiError(400, "热量超出 0–5000 范围")
            fields["kcal"] = round(kcal, 1)
        self.store.update_entry(eid, fields)
        return self._entry_view(self.store.get_entry(eid))

    def delete_entry(self, eid: int) -> None:
        if not self.store.delete_entry(eid):
            raise ApiError(404, "记录不存在")

    @staticmethod
    def _entry_view(row: dict) -> dict:
        return {k: row[k] for k in ("id", "date", "meal", "kind", "name", "grams", "minutes", "kcal",
                                    "protein_g", "carb_g", "fat_g", "confidence", "basis", "raw_text",
                                    "llm_name", "updated_at")}

    # ================= 每日热量差 =================
    def day_summary(self, day: date) -> dict:
        key = day.isoformat()
        entries = [self._entry_view(e) for e in self.store.list_entries(key, key)]
        food = [e for e in entries if e["kind"] == "food"]
        activity = [e for e in entries if e["kind"] == "activity"]
        intake = sum(e["kcal"] for e in food)
        exercise = sum(e["kcal"] for e in activity)
        profile = self.profile_on(day)
        maintenance = profile.get("maintenance_kcal")
        warnings = []
        if maintenance is None:
            burn = balance = None
            warnings.append("未设置维持消耗，热量差无法计算。可在身体数据页填写或让 AI 估算。")
        else:
            burn = maintenance + exercise
            balance = intake - burn
        return {
            "date": key,
            "entries": entries,
            "intake": _round(intake),
            "exercise": _round(exercise),
            "protein_g": _round(sum(e["protein_g"] or 0 for e in food)),
            "carb_g": _round(sum(e["carb_g"] or 0 for e in food)),
            "fat_g": _round(sum(e["fat_g"] or 0 for e in food)),
            "maintenance_kcal": maintenance,
            "burn": _round(burn),
            "balance": _round(balance),
            "weight_kg": profile.get("weight_kg"),
            "warnings": warnings,
        }

    # ================= 周 / 月报告 =================
    @staticmethod
    def period_range(period: str, day: date) -> tuple[date, date]:
        if period == "week":
            start = day - timedelta(days=day.weekday())
            return start, start + timedelta(days=6)
        if period == "month":
            start = day.replace(day=1)
            nxt = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
            return start, nxt - timedelta(days=1)
        raise ApiError(400, "period 只能是 week 或 month")

    def report(self, period: str, day: date, analyze: bool) -> dict:
        start, end = self.period_range(period, day)
        days = [self.day_summary(start + timedelta(days=i)) for i in range((end - start).days + 1)]
        logged = [d for d in days if d["entries"]]
        balances = [d["balance"] for d in logged if d["balance"] is not None]
        weights = [d["weight_kg"] for d in days if d["weight_kg"] is not None]
        n = len(logged)

        def avg(values):
            return _round(sum(values) / len(values)) if values else None

        stats = {
            "period": period,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days_total": len(days),
            "days_logged": n,
            "avg_intake_logged_days": avg([d["intake"] for d in logged]),
            "avg_exercise_logged_days": avg([d["exercise"] for d in logged]),
            "days_with_exercise": sum(1 for d in days if d["exercise"]),
            "total_exercise": _round(sum(d["exercise"] for d in days)),
            "avg_protein_g": avg([d["protein_g"] for d in logged]),
            "avg_carb_g": avg([d["carb_g"] for d in logged]),
            "avg_fat_g": avg([d["fat_g"] for d in logged]),
            "avg_balance_logged_days": avg(balances),
            "total_balance": _round(sum(balances)) if balances else None,
            "weight_first_kg": weights[0] if weights else None,
            "weight_last_kg": weights[-1] if weights else None,
            "weight_change_kg": _round(weights[-1] - weights[0]) if len(weights) >= 2 else None,
            "daily": [{"date": d["date"], "intake": d["intake"], "exercise": d["exercise"],
                       "balance": d["balance"], "entries": len(d["entries"])} for d in days],
        }

        analysis, warnings = None, []
        if analyze:
            if n == 0:
                warnings.append("该时段没有记录，未调用 AI 分析")
            else:
                result, meta = self.run_task("report_analysis", {
                    "period": f"{start.isoformat()} 至 {end.isoformat()}（{period}）",
                    "profile": json.dumps(self.profile_on(end), ensure_ascii=False),
                    "stats": json.dumps(stats, ensure_ascii=False),
                })
                warnings = meta["warnings"]
                analysis = {**result, "llm": meta["llm"], "model": meta["model"]}
        rid = self.store.save_report(period, start.isoformat(), end.isoformat(), stats, analysis)
        return {"id": rid, "period": period, "start": start.isoformat(), "end": end.isoformat(),
                "stats": stats, "analysis": analysis, "warnings": warnings}

    # ================= 连通性测试 =================
    def test_llm(self, pid: str | None) -> dict:
        try:
            profile = self.config.llm_full(pid or None)
        except ConfigError as exc:
            raise ApiError(400, str(exc))
        started = time.time()
        try:
            text = call_llm(profile, 'You are a connectivity test. Reply only with JSON: {"ok": true}', "ping",
                            timeout=60)
            data = parse_json(text)
        except LLMError as exc:
            raise ApiError(502, f"连接失败：{exc}")
        return {"ok": bool(data.get("ok")), "name": profile["name"], "model": profile["model"],
                "latency_ms": int((time.time() - started) * 1000), "reply": text[:200]}

    # ================= 上游可用模型查询 =================
    def list_models(self, body: dict) -> dict:
        """查询某档案的可用模型列表。

        优先按已保存档案的 id 查询（用其完整配置）；档案未保存时，
        允许直接提交表单里临时填写的 protocol / base_url / api_key 查询，
        方便用户在保存前先挑好模型。
        """
        pid = str(body.get("id") or "").strip() or None
        profile = None
        if pid:
            try:
                profile = self.config.llm_full(pid)
            except ConfigError:
                profile = None
        if profile is None:
            protocol = body.get("protocol")
            if protocol not in ("openai", "anthropic"):
                raise ApiError(400, "尚未配置 LLM，请先选择协议并填写接口地址")
            base = str(body.get("base_url") or "").strip().rstrip("/")
            if not base.startswith(("http://", "https://")):
                raise ApiError(400, "接口地址不合法")
            profile = {
                "protocol": protocol,
                "base_url": base,
                "api_key": str(body.get("api_key") or "").strip(),
            }
        if not profile.get("api_key"):
            raise ApiError(400, "请先填写 API Key，或选择已保存的档案后再获取模型")
        try:
            models = llm_list_models(profile)
        except LLMError as exc:
            raise ApiError(502, f"获取模型列表失败：{exc}")
        return {"models": models, "count": len(models)}

    def test_search(self, query: str) -> dict:
        cfg = self.config.search_full()
        if cfg["provider"] == "none":
            raise ApiError(400, "当前未启用联网搜索")
        try:
            rows = search(cfg, query or "热量 每100克")
        except SearchError as exc:
            raise ApiError(502, f"搜索失败：{exc}")
        return {"count": len(rows), "results": rows[:5]}
