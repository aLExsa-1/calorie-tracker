# 模型路由参考资料（按需读取，不要常驻上下文）

> 本文件从旧版 CLAUDE.md 拆出。价格与基准数据沿用旧版，记录核实日期 2026-10-12；我无法独立验证，开大任务前请到 OpenRouter 复查加权实付价。

## 价格（输入/输出，美元每百万 token）

| 模型 | 价格 | 备注 |
|---|---|---|
| Sonnet 5.5 | $2 / $10，缓存读 $0.10 | 编排与审查 |
| GLM 5.3 | 加权实付约 $0.22 / $4.29，多 provider 低至 $0.07 / $3.40 | reasoning effort 三档 low/high/max，默认 max |
| Kimi K3 | 加权实付约 $0.46 / $14.72 | 默认持续思考；缓存命中约 93%，有效输入约 $0.485；走 Standard 路由即可 |
| Haiku 5.5 | ≤10 万 token 请求 $0.10 / $0.50；超过 10 万跳到 $0.50 / $2.50 | 计费断崖，资料先压缩 |

## 选型依据（旧版记录）

- GLM 5.3 的 Terminal-Bench 4.0 得分 41.9，约为 K3（12.6）的 3 倍，所以执行类工兵活归 GLM。
- Kimi K3 视觉榜单四者最强，原生多模态，Androidnative 榜前 14%，1M 上下文，适合看图迭代与大仓库调研。
- 重构方案设计放 GLM max：输出价 $4.3/M，低于 Sonnet 的 $10/M。
- agent 任务约 80% 的 token 花在翻资料上，因此把翻资料压给 Haiku 是最大的省钱杠杆。

## 建议的权限硬拦截（`.claude/settings.json`，当前不存在，需用户自行决定是否创建）

```json
{
  "permissions": {
    "deny": [
      "Read(./data/**)",
      "Read(./android/keystore.properties)",
      "Read(./.android-build/keystore/**)",
      "Read(./.android-build/tools/**)",
      "Read(./android/app/build/**)"
    ]
  }
}
```

前三条防密钥外泄，后两条防检索时扫进几万个无关文件。

## 建议补进 `.gitignore` 的条目

```
data/
docs/archive/
```

## 使用 Kimi / GLM 的前提

Claude Desktop 的子代理 `model` 参数只接受 sonnet/opus/haiku/fable 别名。要让路由表里的 GLM、Kimi 真正被分派，需要在 OpenRouter 或网关侧把这些别名映射到对应模型，或者手动切换模型开新会话并通过 `docs/tasks/*.md` 交接。未确认映射关系前，不要假定分派能成功。
