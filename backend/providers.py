"""LLM 提供商预设：内置当前热门服务商的接口地址与常用模型名。

数据于 2026-10 依各官方文档核实（DeepSeek / 智谱 / Kimi / 百炼为官方文档原文，
OpenAI / Anthropic / xAI / Qwen 等经 OpenRouter 模型列表交叉核实）。
模型名会随厂商更新而过时：界面提供「获取可用模型」，直接查询服务商的
模型列表接口（OpenAI 协议 GET /models，Anthropic 协议 GET /v1/models），
预设里的 models 仅作初始参考。
"""
from __future__ import annotations

PROVIDERS = [
    {
        "id": "deepseek",
        "label": "DeepSeek（深度求索）",
        "protocol": "openai",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "note": "也支持 Anthropic 协议，接口地址改为 https://api.deepseek.com/anthropic",
    },
    {
        "id": "zhipu",
        "label": "智谱 AI（GLM）",
        "protocol": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-5.3", "glm-5.3-flash", "glm-5.2"],
        "note": "",
    },
    {
        "id": "moonshot",
        "label": "Kimi（月之暗面）",
        "protocol": "openai",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k3", "kimi-k2.6"],
        "note": "也支持 Anthropic 协议，接口地址改为 https://api.moonshot.cn/anthropic",
    },
    {
        "id": "dashscope",
        "label": "阿里云百炼（通义千问 Qwen）",
        "protocol": "openai",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen3.8-max", "qwen3.7-plus", "qwen3.8-flash"],
        "note": "需在阿里云百炼控制台创建 API Key",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "protocol": "openai",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-6-astra", "gpt-6-sol", "gpt-6-luna"],
        "note": "",
    },
    {
        "id": "anthropic",
        "label": "Anthropic（Claude）",
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com",
        "models": ["claude-sonnet-5.5", "claude-haiku-5.5", "claude-opus-5.5"],
        "note": "",
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "protocol": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.5-flash"],
        "note": "OpenAI 兼容端点；部分地区网络无法直连",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter（聚合平台）",
        "protocol": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["deepseek/deepseek-v4.1-flash", "z-ai/glm-5.3", "qwen/qwen3.8-max"],
        "note": "一个 Key 调用多家模型；模型名格式为 厂商/模型",
    },
    {
        "id": "siliconflow",
        "label": "硅基流动 SiliconFlow（聚合平台）",
        "protocol": "openai",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [],
        "note": "国内聚合平台，含免费模型；请点「获取可用模型」查询",
    },
    {
        "id": "xai",
        "label": "xAI（Grok）",
        "protocol": "openai",
        "base_url": "https://api.x.ai/v1",
        "models": ["grok-4.7"],
        "note": "",
    },
    {
        "id": "volcark",
        "label": "火山方舟（豆包 Doubao）",
        "protocol": "openai",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-seed-1.6"],
        "note": "需在火山方舟控制台开通模型；请点「获取可用模型」查询",
    },
    {
        "id": "mistral",
        "label": "Mistral AI",
        "protocol": "openai",
        "base_url": "https://api.mistral.ai/v1",
        "models": ["mistral-large-4-0"],
        "note": "",
    },
    {
        "id": "minimax",
        "label": "MiniMax",
        "protocol": "openai",
        "base_url": "https://api.minimaxi.com/v1",
        "models": ["MiniMax-M3"],
        "note": "",
    },
]


def providers_view() -> list[dict]:
    """对外视图：浅拷贝，避免调用方改动内置数据。"""
    return [dict(p) for p in PROVIDERS]
