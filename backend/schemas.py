"""AI 输出的结构与取值范围规则。

AI 负责给出数值，这里只做校验：类型、必填项、合理范围。
校验失败时接口返回 422 并附上原始输出，不会把错误数据写入记录。
"""
from __future__ import annotations

from typing import Any, Callable


class SchemaError(ValueError):
    """AI 输出不符合规则。"""


def _num(value: Any, path: str, lo: float, hi: float, required: bool = True):
    if value is None or value == "":
        if required:
            raise SchemaError(f"{path} 缺失")
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise SchemaError(f"{path} 不是数字：{value!r}")
    if not lo <= x <= hi:
        raise SchemaError(f"{path}={x:g} 超出合理范围 [{lo:g}, {hi:g}]")
    return round(x, 1)


def _str(value: Any, default: str = "") -> str:
    return default if value is None else str(value).strip()


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        raise SchemaError("应为字符串数组")
    return [str(x).strip() for x in value if str(x).strip()]


def _items(data: dict, max_items: int = 50) -> list[dict]:
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise SchemaError("items 必须是非空数组")
    if len(items) > max_items:
        raise SchemaError(f"items 数量超过 {max_items}")
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise SchemaError(f"items[{i}] 不是对象")
    return items


def _food(data: dict) -> dict:
    out = []
    for i, it in enumerate(_items(data)):
        p = f"items[{i}]"
        name = _str(it.get("name"))
        if not name:
            raise SchemaError(f"{p}.name 缺失")
        confidence = _str(it.get("confidence"), "medium").lower()
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"
        out.append({
            "name": name,
            "grams": _num(it.get("grams"), f"{p}.grams", 0, 10000, required=False),
            "kcal": _num(it.get("kcal"), f"{p}.kcal", 0, 5000),
            "protein_g": _num(it.get("protein_g"), f"{p}.protein_g", 0, 1000, required=False),
            "carb_g": _num(it.get("carb_g"), f"{p}.carb_g", 0, 1000, required=False),
            "fat_g": _num(it.get("fat_g"), f"{p}.fat_g", 0, 1000, required=False),
            "confidence": confidence,
            "basis": _str(it.get("basis")),
        })
    return {"items": out, "notes": _str(data.get("notes"))}


def _activity(data: dict) -> dict:
    out = []
    for i, it in enumerate(_items(data)):
        p = f"items[{i}]"
        name = _str(it.get("name"))
        if not name:
            raise SchemaError(f"{p}.name 缺失")
        out.append({
            "name": name,
            "minutes": _num(it.get("minutes"), f"{p}.minutes", 0, 1440, required=False),
            "kcal": _num(it.get("kcal"), f"{p}.kcal", 0, 3000),
            "basis": _str(it.get("basis")),
        })
    return {"items": out, "notes": _str(data.get("notes"))}


def _metabolism(data: dict) -> dict:
    bmr = _num(data.get("bmr_kcal"), "bmr_kcal", 300, 5000)
    maintenance = _num(data.get("maintenance_kcal"), "maintenance_kcal", 500, 8000)
    if maintenance < bmr:
        raise SchemaError("maintenance_kcal 不应低于 bmr_kcal")
    return {"bmr_kcal": bmr, "maintenance_kcal": maintenance, "basis": _str(data.get("basis"))}


def _report(data: dict) -> dict:
    return {
        "summary": _str(data.get("summary")),
        "diet_score": _num(data.get("diet_score"), "diet_score", 0, 100),
        "exercise_score": _num(data.get("exercise_score"), "exercise_score", 0, 100),
        "exercise_level": _str(data.get("exercise_level")),
        "diet_comments": _str_list(data.get("diet_comments")),
        "exercise_comments": _str_list(data.get("exercise_comments")),
        "suggestions": _str_list(data.get("suggestions")),
        "risks": _str_list(data.get("risks")),
    }


VALIDATORS: dict[str, Callable[[dict], dict]] = {
    "food_estimate": _food,
    "activity_estimate": _activity,
    "metabolism_estimate": _metabolism,
    "report_analysis": _report,
}


def validate(task: str, data: Any) -> dict:
    if not isinstance(data, dict):
        raise SchemaError("顶层必须是 JSON 对象")
    return VALIDATORS[task](data)
