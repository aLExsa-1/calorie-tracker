"""联网搜索适配器：searxng / tavily / brave。由设置页配置，provider=none 时不搜索。"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = {
    "tavily": "https://api.tavily.com",
    "brave": "https://api.search.brave.com/res/v1/web/search",
}


class SearchError(Exception):
    """搜索失败。调用方应跳过搜索并继续，不中断主流程。"""


def _request_json(req: urllib.request.Request, timeout: float = 20) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        with exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise SearchError(f"HTTP {exc.code}：{detail}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SearchError(f"请求失败：{exc}")


def _get_json(url: str, headers: dict | None = None) -> dict:
    return _request_json(urllib.request.Request(url, headers=headers or {}))


def _post_json(url: str, body: dict) -> dict:
    return _request_json(urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    ))


def search(cfg: dict, query: str, limit: int = 5) -> list[dict]:
    """返回 [{title, url, snippet}, ...]。"""
    provider = cfg.get("provider", "none")
    if provider == "none" or not query.strip():
        return []
    base = (cfg.get("base_url") or DEFAULT_BASE.get(provider, "")).rstrip("/")
    key = cfg.get("api_key", "")

    if provider == "searxng":
        if not base:
            raise SearchError("searxng 需要填写 base_url")
        data = _get_json(f"{base}/search?" + urllib.parse.urlencode({"q": query, "format": "json"}))
        rows = [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in data.get("results", [])]
    elif provider == "tavily":
        if not key:
            raise SearchError("tavily 需要 api_key")
        data = _post_json(f"{base}/search", {"api_key": key, "query": query, "max_results": limit})
        rows = [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                for r in data.get("results", [])]
    elif provider == "brave":
        if not key:
            raise SearchError("brave 需要 api_key")
        url = f"{base}?" + urllib.parse.urlencode({"q": query, "count": limit})
        data = _get_json(url, {"X-Subscription-Token": key, "Accept": "application/json"})
        rows = [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
                for r in data.get("web", {}).get("results", [])]
    else:
        raise SearchError(f"未知搜索服务：{provider}")
    return rows[:limit]


def format_results(rows: list[dict]) -> str:
    return "\n".join(f"[{i}] {r['title']} ({r['url']})\n{r['snippet']}" for i, r in enumerate(rows, 1))
