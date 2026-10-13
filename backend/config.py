"""可配置项：LLM 档案、联网搜索服务、各任务提示词、任务→模型映射。持久化为 JSON 文件。

注意：API Key 以明文保存在本地 data/config.json 中，接口返回时只显示末 4 位。
"""
from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from pathlib import Path

from .prompts import DEFAULT_PROMPTS, OUTPUT_FORMAT, TASKS

PROTOCOLS = ("openai", "anthropic")
SEARCH_PROVIDERS = ("none", "searxng", "tavily", "brave")
PROMPT_FIELDS = ("system", "user", "use_search", "search_query")


class ConfigError(Exception):
    """配置不完整或不合法。"""


def _mask(item: dict) -> dict:
    out = dict(item)
    key = out.pop("api_key", "") or ""
    out["api_key_set"] = bool(key)
    out["api_key_hint"] = ("…" + key[-4:]) if len(key) >= 8 else ("已设置" if key else "")
    return out


def _clean_url(value, field: str, required: bool) -> str:
    url = str(value or "").strip().rstrip("/")
    if not url:
        if required:
            raise ConfigError(f"{field} 不能为空")
        return ""
    if not url.startswith(("http://", "https://")):
        raise ConfigError(f"{field} 必须以 http:// 或 https:// 开头")
    return url


class Config:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data: dict = {
            "llm_profiles": [],
            "active_llm_id": None,
            "task_llm": {},
            "search": {"provider": "none", "base_url": "", "api_key": ""},
            "prompt_overrides": {},
        }
        if self.path.exists():
            text = self.path.read_text(encoding="utf-8").strip()
            if text:
                self.data.update(json.loads(text))

    # ---------- 持久化 ----------
    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---------- 对外视图（不含明文 Key） ----------
    def export_view(self) -> dict:
        """导出用的配置快照：与界面可见内容一致，**不含任何明文 API Key**。"""
        with self._lock:
            return {
                "llm_profiles": [_mask(p) for p in self.data["llm_profiles"]],
                "active_llm_id": self.data["active_llm_id"],
                "task_llm": dict(self.data["task_llm"]),
                "search": _mask(self.data["search"]),
                "prompt_overrides": dict(self.data["prompt_overrides"]),
            }

    def public(self) -> dict:
        with self._lock:
            return {
                "llm_profiles": [_mask(p) for p in self.data["llm_profiles"]],
                "active_llm_id": self.data["active_llm_id"],
                "task_llm": dict(self.data["task_llm"]),
                "search": _mask(self.data["search"]),
                "prompts": {t: self.prompt(t) for t in TASKS},
                "tasks": [{"id": t, "label": v["label"], "uses_search": v["uses_search"]} for t, v in TASKS.items()],
                "output_formats": OUTPUT_FORMAT,
                "protocols": list(PROTOCOLS),
                "search_providers": list(SEARCH_PROVIDERS),
            }

    # ---------- LLM 档案 ----------
    def _find_llm(self, pid: str) -> dict | None:
        return next((p for p in self.data["llm_profiles"] if p["id"] == pid), None)

    def upsert_llm(self, body: dict) -> str:
        with self._lock:
            pid = str(body.get("id") or "").strip() or uuid.uuid4().hex[:10]
            existing = self._find_llm(pid) or {}
            name = str(body.get("name") or "").strip()
            if not name:
                raise ConfigError("档案名称不能为空")
            protocol = body.get("protocol")
            if protocol not in PROTOCOLS:
                raise ConfigError(f"协议必须是 {' / '.join(PROTOCOLS)}")
            model = str(body.get("model") or "").strip()
            if not model:
                raise ConfigError("模型名不能为空")
            try:
                temperature = float(body.get("temperature", 0.2))
                max_tokens = int(body.get("max_tokens", 4096))
            except (TypeError, ValueError):
                raise ConfigError("temperature 或 max_tokens 不是数字")
            if not 0 <= temperature <= 2:
                raise ConfigError("temperature 应在 0–2 之间")
            if not 256 <= max_tokens <= 64000:
                raise ConfigError("max_tokens 应在 256–64000 之间")
            extra = str(body.get("extra_body") or "").strip()
            if extra:
                try:
                    if not isinstance(json.loads(extra), dict):
                        raise ConfigError("extra_body 必须是 JSON 对象")
                except json.JSONDecodeError as exc:
                    raise ConfigError(f"extra_body 不是合法 JSON：{exc}")
            key = str(body.get("api_key") or "").strip() or existing.get("api_key", "")
            profile = {
                "id": pid,
                "name": name,
                "protocol": protocol,
                "base_url": _clean_url(body.get("base_url"), "base_url", required=True),
                "api_key": key,
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "json_mode": bool(body.get("json_mode", True)),
                "extra_body": extra,
            }
            profiles = self.data["llm_profiles"]
            if existing:
                profiles[profiles.index(existing)] = profile
            else:
                profiles.append(profile)
            if not self.data["active_llm_id"]:
                self.data["active_llm_id"] = pid
            self._save()
            return pid

    def delete_llm(self, pid: str) -> None:
        with self._lock:
            if not self._find_llm(pid):
                raise ConfigError("档案不存在")
            self.data["llm_profiles"] = [p for p in self.data["llm_profiles"] if p["id"] != pid]
            if self.data["active_llm_id"] == pid:
                self.data["active_llm_id"] = self.data["llm_profiles"][0]["id"] if self.data["llm_profiles"] else None
            self.data["task_llm"] = {t: v for t, v in self.data["task_llm"].items() if v != pid}
            self._save()

    def activate_llm(self, pid: str) -> None:
        with self._lock:
            if not self._find_llm(pid):
                raise ConfigError("档案不存在")
            self.data["active_llm_id"] = pid
            self._save()

    def set_task_llm(self, mapping: dict) -> None:
        with self._lock:
            for task, pid in mapping.items():
                if task not in TASKS:
                    raise ConfigError(f"未知任务：{task}")
                if pid and not self._find_llm(pid):
                    raise ConfigError(f"档案不存在：{pid}")
            self.data["task_llm"] = {t: p for t, p in mapping.items() if p}
            self._save()

    def llm_full(self, pid: str | None = None) -> dict:
        """返回含明文 Key 的档案，仅供后端调用。"""
        with self._lock:
            target = self._find_llm(pid) if pid else None
            if target is None and pid is None:
                target = self._find_llm(self.data["active_llm_id"] or "")
            if target is None:
                raise ConfigError("尚未配置 LLM，请到设置页添加并设为默认")
            return deepcopy(target)

    def resolve_llm(self, task: str) -> dict:
        with self._lock:
            pid = self.data["task_llm"].get(task)
            if pid and self._find_llm(pid):
                return self.llm_full(pid)
            return self.llm_full()

    # ---------- 搜索 ----------
    def set_search(self, body: dict) -> None:
        with self._lock:
            provider = body.get("provider", "none")
            if provider not in SEARCH_PROVIDERS:
                raise ConfigError(f"搜索服务必须是 {' / '.join(SEARCH_PROVIDERS)}")
            base = _clean_url(body.get("base_url"), "base_url", required=provider == "searxng")
            key = str(body.get("api_key") or "").strip() or self.data["search"].get("api_key", "")
            if provider in ("tavily", "brave") and not key:
                raise ConfigError(f"{provider} 需要 API Key")
            self.data["search"] = {"provider": provider, "base_url": base, "api_key": key}
            self._save()

    def search_full(self) -> dict:
        with self._lock:
            return deepcopy(self.data["search"])

    # ---------- 提示词 ----------
    def prompt(self, task: str) -> dict:
        if task not in TASKS:
            raise ConfigError(f"未知任务：{task}")
        effective = {**deepcopy(DEFAULT_PROMPTS[task]), **self.data["prompt_overrides"].get(task, {})}
        effective["label"] = TASKS[task]["label"]
        return {k: effective[k] for k in (*PROMPT_FIELDS, "label")}

    def set_prompt(self, task: str, body: dict) -> None:
        with self._lock:
            if task not in TASKS:
                raise ConfigError(f"未知任务：{task}")
            system = str(body.get("system") or "").strip()
            user = str(body.get("user") or "").strip()
            if not system or not user:
                raise ConfigError("系统提示词和用户模板不能为空")
            self.data["prompt_overrides"][task] = {
                "system": system,
                "user": user,
                "use_search": bool(body.get("use_search", TASKS[task]["uses_search"])),
                "search_query": str(body.get("search_query") or "").strip(),
            }
            self._save()

    def reset_prompt(self, task: str) -> None:
        with self._lock:
            if task not in TASKS:
                raise ConfigError(f"未知任务：{task}")
            self.data["prompt_overrides"].pop(task, None)
            self._save()
