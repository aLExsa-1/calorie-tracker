"""AI 任务清单、默认提示词、输出格式约定。

- DEFAULT_PROMPTS：用户可在设置页自由修改（修改后保存在 data/config.json 的 prompt_overrides 中）。
- OUTPUT_FORMAT：输出结构由后端规则固定，会自动追加到系统提示词末尾，保证程序能解析。
  用户改提示词时不需要关心 JSON 格式。

占位符：{input} 用户输入，{meal} 餐次，{profile} 身体数据 JSON，{period} 时段，
        {stats} 统计数据 JSON，{search} 联网搜索结果块（没有搜索时为空）。
"""

TASKS = {
    "food_estimate": {"label": "饮食热量估算", "uses_search": True},
    "activity_estimate": {"label": "运动消耗估算", "uses_search": True},
    "metabolism_estimate": {"label": "基础代谢与维持消耗", "uses_search": False},
    "report_analysis": {"label": "周期报告分析", "uses_search": False},
}

SEARCH_BLOCK = "参考联网搜索结果（可能不准确，请结合常识判断）：\n{results}"

OUTPUT_FORMAT = {
    "food_estimate": (
        '{"items":[{"name":"食物名","grams":数字或null,"kcal":数字,"protein_g":数字,'
        '"carb_g":数字,"fat_g":数字,"confidence":"high|medium|low","basis":"估算依据与份量假设"}],'
        '"notes":"整体说明"}'
    ),
    "activity_estimate": (
        '{"items":[{"name":"运动名","minutes":数字,"kcal":数字,"basis":"估算依据"}],'
        '"notes":"整体说明"}\n'
        "其中 kcal 是「超过静息代谢的额外消耗」（净增量），需结合用户体重计算。"
    ),
    "metabolism_estimate": (
        '{"bmr_kcal":数字,"maintenance_kcal":数字,"basis":"估算依据"}\n'
        "bmr_kcal 为基础代谢率；maintenance_kcal 为日常维持消耗（不含刻意运动）。"
    ),
    "report_analysis": (
        '{"summary":"总体结论","diet_score":0到100的整数,"exercise_score":0到100的整数,'
        '"exercise_level":"如 入门/规律/进阶","diet_comments":["..."],'
        '"exercise_comments":["..."],"suggestions":["具体可执行的建议"],"risks":["需要注意或就医的风险"]}'
    ),
}

DEFAULT_PROMPTS = {
    "food_estimate": {
        "system": (
            "你是专业的营养师和食物热量估算助手。根据用户描述估算每种食物的热量与三大营养素。"
            "用户未给出份量时，按常见份量假设并在 basis 中写明。"
            "如果提供了联网搜索结果，优先参考其中的营养数据。"
        ),
        "user": "用户饮食描述：{input}\n餐次：{meal}\n用户身体数据（可能为空）：{profile}\n{search}",
        "use_search": True,
        "search_query": "{input} 热量 营养成分 每100克",
    },
    "activity_estimate": {
        "system": (
            "你是运动科学助手。根据运动描述估算消耗。"
            "kcal 为超过静息代谢的额外消耗；结合用户体重计算；未给出时长时按常见时长假设并说明。"
            "如果提供了联网搜索结果，优先参考其中的 MET 或千卡消耗数据。"
        ),
        "user": "用户运动描述：{input}\n用户身体数据（可能为空）：{profile}\n{search}",
        "use_search": True,
        "search_query": "{input} 运动 千卡消耗 MET",
    },
    "metabolism_estimate": {
        "system": (
            "你是代谢与营养估算助手。根据用户的性别、年龄、身高、体重和活动情况，"
            "估算基础代谢率和日常维持消耗（不含刻意运动）。"
        ),
        "user": "用户身体数据：{profile}\n{search}",
        "use_search": False,
        "search_query": "基础代谢 BMR 估算",
    },
    "report_analysis": {
        "system": (
            "你是健康管理分析师。根据用户一段时间的热量统计数据，评价饮食结构与热量控制、"
            "运动量与规律性，并给出具体可执行的建议。数据缺失时说明局限。"
            "你不是医生：如有疾病相关风险，请提示就医。"
        ),
        "user": "统计时段：{period}\n用户身体数据：{profile}\n统计数据(JSON)：{stats}\n{search}",
        "use_search": False,
        "search_query": "",
    },
}
