"""通用 LLM 调用层：支持 OpenAI 兼容协议与 Anthropic 协议，地址、Key、模型均由配置决定。

联网搜索有两种方式（在设置页配置）：
1. 程序侧搜索：由 search.py 调用搜索服务，结果拼进提示词（适用于任何模型）。
2. 模型原生搜索：在 LLM 档案的 extra_body（JSON）里写入厂商的工具声明，
   例如 Anthropic 的 {"tools":[{"type":"web_search_20250305","name":"web_search","max_uses":3}]}。
   extra_body 会被合并进请求体，因此可以适配各家的参数。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class LLMError(Exception):
    """LLM 调用失败（网络、HTTP 错误、输出无法解析）。"""


def _extra(profile: dict) -> dict:
    raw = profile.get("extra_body") or ""
    if isinstance(raw, dict):
        return raw
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"extra_body 不是合法 JSON：{exc}")
    if not isinstance(value, dict):
        raise LLMError("extra_body 必须是 JSON 对象")
    return value


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        with exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise LLMError(f"HTTP {exc.code}：{detail}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LLMError(f"请求失败：{exc}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise LLMError("接口返回的不是 JSON")


def call_llm(profile: dict, system: str, user: str, timeout: float = 120, images: list | None = None) -> str:
    """调用一次模型，返回文本内容。"""
    protocol = profile.get("protocol")
    base = str(profile.get("base_url", "")).rstrip("/")
    key = profile.get("api_key", "")
    model = profile.get("model", "")
    temperature = float(profile.get("temperature", 0.2))
    extra = _extra(profile)
    images = images or []

    if protocol == "openai":
        user_content: object = user
        if images:
            user_content = [{"type": "text", "text": user}] + [
                {"type": "image_url", "image_url": {"url": f"data:{img['mime']};base64,{img['data']}"}}
                for img in images
            ]
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "max_tokens": int(profile.get("max_tokens", 4096)),
        }
        if profile.get("json_mode", True):
            body["response_format"] = {"type": "json_object"}
        body.update(extra)
        data = _post(f"{base}/chat/completions", body,
                     {"Authorization": f"Bearer {key}"}, timeout)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"响应结构不符合 OpenAI 格式：{str(data)[:300]}")

    if protocol == "anthropic":
        url = f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"
        body = {
            "model": model,
            "max_tokens": int(profile.get("max_tokens", 4096)),
            "system": system,
            "messages": [{"role": "user", "content": _anthropic_content(user, images)}],
            "temperature": temperature,
        }
        body.update(extra)
        data = _post(url, body, {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
        blocks = data.get("content")
        if not isinstance(blocks, list):
            raise LLMError(f"响应结构不符合 Anthropic 格式：{str(data)[:300]}")
        return "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")

    raise LLMError(f"不支持的协议：{protocol}")


def _anthropic_content(user: str, images: list) -> object:
    if not images:
        return user
    blocks = [{"type": "image", "source": {"type": "base64", "media_type": img["mime"], "data": img["data"]}} for img in images]
    return blocks + [{"type": "text", "text": user}]


def parse_json(text: str) -> dict:
    """从模型输出中取出 JSON 对象（容忍代码块包裹和前后多余文字）。"""
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    for candidate in (stripped, stripped[stripped.find("{"): stripped.rfind("}") + 1]):
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(value, dict):
            return value
    raise LLMError("模型输出中没有可解析的 JSON 对象")
