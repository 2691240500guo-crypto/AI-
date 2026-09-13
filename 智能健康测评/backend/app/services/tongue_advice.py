"""舌象观察的通俗解读与生活建议。

把检测模型的原始输出（舌色 / 苔质 / 厚薄 / 形态特征）翻译成用户看得懂的话和能执行的动作。
严格定位为「健康观察参考」：不做诊断、不给药物建议、不承诺疗效。

v2（2026-09-11）：取值随检测模型类别更新 ——
  舌色：淡红 / 红 / 暗红（另保留「淡白」兼容历史记录）
  苔质：白苔 / 黄苔 / 滑苔 / 剥苔 / 薄白
并新增「苔的厚薄」与「形态特征」（齿痕 / 裂纹 / 胖大 / 瘦小 / 红点 / 分区凹陷）解读。
"""

# ---------------- 舌色 ----------------
COLOR_INFO: dict[str, dict] = {
    "淡红": {
        "label": "淡红（常见）",
        "plain": "舌色淡红，属于常见范围。",
        "tips": ["保持现在规律的三餐和作息即可"],
    },
    "红": {
        "label": "偏红",
        "plain": "舌色偏红，常见于近期偏上火、睡眠不足、饮水偏少或辛辣刺激吃得较多。",
        "tips": [
            "把每日饮水补到 1500–2000 毫升，少量多次",
            "这几天少吃辛辣、油炸、烧烤，酒先停一停",
            "尽量在 23:30 前入睡，保证 7 小时以上睡眠",
            "连续观察 3–5 天，再看舌色是否变淡",
        ],
    },
    "暗红": {
        "label": "偏暗红（紫暗）",
        "plain": "舌色偏暗、偏紫，常见于近期疲劳熬夜、久坐少动、天冷受寒或气血运行不畅。",
        "tips": [
            "每天安排 20–30 分钟快走或拉伸，别久坐",
            "注意保暖，尤其是手脚和腰腹",
            "少吃生冷冰饮，餐食尽量温热",
            "保证睡眠，连续观察 3–5 天看颜色是否转淡红",
        ],
    },
    "淡白": {
        "label": "偏淡",
        "plain": "舌色比常见的淡红偏淡一些，常见于近期比较疲劳、饮食摄入不足或气血偏弱。",
        "tips": [
            "每餐安排一份优质蛋白：鸡蛋、瘦肉、鱼虾或豆制品",
            "适当增加含铁食物：瘦牛肉、动物肝脏、菠菜、黑木耳",
            "避免过度节食和连续熬夜，尽量睡够 7 小时",
        ],
    },
}

# ---------------- 苔质 ----------------
COAT_INFO: dict[str, dict] = {
    "白苔": {
        "label": "白苔",
        "plain": "舌面覆盖白色舌苔，常见于近期受凉、饮食生冷或消化功能偏弱。",
        "tips": [
            "这几餐以温热、易消化的食物为主，少吃生冷和冰饮",
            "主食里加一点杂粮或薯类，帮助消化",
            "注意腹部保暖，饭后别马上躺下",
        ],
    },
    "黄苔": {
        "label": "黄苔",
        "plain": "舌面苔色偏黄，多与饮食偏油辣、饮水不足或消化负担偏重有关。",
        "tips": [
            "先清淡饮食 3–5 天：以蒸煮为主，少油少辣",
            "多喝水，少吃烧烤火锅和油腻外卖，酒先停",
            "增加蔬菜和粗粮，帮助肠道蠕动",
            "如果同时有口苦、口臭、腹胀或反酸，建议去消化内科看看",
        ],
    },
    "滑苔": {
        "label": "滑苔（水分偏多）",
        "plain": "舌面看起来偏湿润、水滑，常与近期水分代谢偏慢、饮食偏甜腻或久坐有关。",
        "tips": [
            "少喝含糖饮料，夜里别大量喝水",
            "每餐加一份蔬菜，减少甜食和油腻",
            "每天活动 20–30 分钟，久坐时每小时起身走动",
        ],
    },
    "剥苔": {
        "label": "剥苔（部分无苔）",
        "plain": "舌面局部苔缺失、露出舌质，常见于近期饮食不规律、疲劳或消化功能波动。",
        "tips": [
            "三餐定时定量，避免长时间空腹或暴饮暴食",
            "饮食以温和易消化为主，少辛辣刺激",
            "保证睡眠，观察几天是否恢复均匀薄白苔",
            "若长期存在或伴随明显不适，建议就医面诊",
        ],
    },
    "薄白（无明显苔色）": {
        "label": "薄白（常见）",
        "plain": "舌苔薄白、分布均匀，属于常见表现。",
        "tips": ["继续保持清淡均衡的饮食"],
    },
    # ---- 历史记录兼容项 ----
    "薄白": {
        "label": "薄白（常见）",
        "plain": "舌苔薄白、分布均匀，属于常见表现。",
        "tips": ["继续保持清淡均衡的饮食"],
    },
    "厚腻": {
        "label": "偏厚腻",
        "plain": "舌苔偏厚、偏黏腻，常与近期吃得偏油、消化负担重或作息不规律有关。",
        "tips": [
            "减少油炸、奶油、甜点和夜宵",
            "每餐加一份蔬菜，主食换成杂粮或薯类，增加膳食纤维",
            "饭后散步 10–15 分钟，不要马上躺下",
        ],
    },
    "黄腻": {
        "label": "偏黄厚",
        "plain": "舌苔偏黄、偏厚腻，多与饮食偏油辣、饮水不足或消化负担有关。",
        "tips": [
            "先清淡饮食 3–5 天：以蒸煮为主，少油少辣",
            "多喝水，少吃烧烤火锅和油腻外卖，酒先停",
            "增加蔬菜和粗粮，帮助肠道蠕动",
        ],
    },
}

# ---------------- 苔的覆盖范围 ----------------
# ⚠️ 这里刻意不叫「厚苔/薄苔」：TCM-Tongue 数据集的苔类标注是整舌级大框，
#    实测面积占比全部落在 0.71~1.00，无法区分厚薄（详见 tongue_service.py 顶部注释）。
#    只给「覆盖较广 / 较少」这种可解释的观察描述；真正的厚薄需要临床标注。
THICKNESS_INFO: dict[str, dict] = {
    "苔覆盖较广": {
        "label": "苔覆盖较广",
        "plain": "舌面大部分区域可见舌苔覆盖。注意：这里反映的是「覆盖范围」，"
                 "苔的实际厚薄需要临床面诊判断。",
        "tips": [
            "减少油炸、奶油、甜点和夜宵",
            "主食换成杂粮或薯类，每餐加一份蔬菜",
            "饭后散步 10–15 分钟，不要马上躺下",
        ],
    },
    "苔覆盖较少": {
        "label": "苔覆盖较少",
        "plain": "舌面只有少部分区域可见舌苔覆盖，属于常见表现。",
        "tips": ["保持规律饮食即可"],
    },
}

# ---------------- 形态特征 ----------------
MORPHOLOGY_INFO: dict[str, dict] = {
    "齿痕舌": {
        "label": "齿痕舌",
        "plain": "舌边缘可见牙齿压出的痕迹，常与疲劳、久坐、饮食偏甜腻有关。",
        "tips": ["减少甜食和油腻，规律作息", "每天适度活动 20–30 分钟"],
    },
    "裂纹舌": {
        "label": "裂纹舌",
        "plain": "舌面可见裂纹或沟纹，多为长期存在，常与体质偏干、饮水偏少有关。",
        "tips": ["饮水补到 1500–2000 毫升", "多吃蔬果，少吃辛辣烧烤"],
    },
    "胖大舌": {
        "label": "舌体偏胖大",
        "plain": "舌体看起来偏宽大、偏厚，常与饮食偏咸偏甜、水分代谢偏慢有关。",
        "tips": ["控制盐分，少吃腌制和重口味", "规律运动，避免久坐"],
    },
    "瘦小舌": {
        "label": "舌体偏瘦小",
        "plain": "舌体偏瘦薄，常见于近期饮食摄入不足、疲劳或体重下降期间。",
        "tips": ["保证三餐热量与优质蛋白", "避免过度节食"],
    },
    "红点舌": {
        "label": "舌面红点（点刺）",
        "plain": "舌面可见细小红色点状突起，常与近期上火、熬夜或辛辣饮食有关。",
        "tips": ["这几天清淡饮食，少吃辛辣烧烤", "早点睡，多喝水"],
    },
    "肝区凹陷": {
        "label": "肝胆区偏凹陷（观察项）",
        "plain": "舌边肝胆对应区域看起来偏凹陷，仅为图像观察，供参考。",
        "tips": ["规律作息，少熬夜", "控制饮酒"],
    },
    "肾区凹陷": {
        "label": "肾区偏凹陷（观察项）",
        "plain": "舌根肾对应区域看起来偏凹陷，仅为图像观察，供参考。",
        "tips": ["注意休息，避免过度劳累", "规律作息，保证睡眠"],
    },
    "心肺区凹陷": {
        "label": "心肺区偏凹陷（观察项）",
        "plain": "舌尖心肺对应区域看起来偏凹陷，仅为图像观察，供参考。",
        "tips": ["注意规律睡眠，适度有氧运动"],
    },
}

# 模型输出里可能出现的非标准写法，做宽松归一化
COLOR_ALIAS = {
    "淡白": "淡白", "偏淡": "淡白", "淡红": "淡红", "红": "红", "偏红": "红",
    "暗红": "暗红", "偏暗红": "暗红", "紫暗": "暗红", "颜色不明确": "淡红",
}
COAT_ALIAS = {
    "薄白": "薄白", "薄白（无明显苔色）": "薄白（无明显苔色）", "无明显苔色": "薄白（无明显苔色）",
    "白苔": "白苔", "黄苔": "黄苔", "滑苔": "滑苔", "剥苔": "剥苔",
    "厚腻": "厚腻", "黄腻": "黄腻", "偏厚或有覆盖感": "厚腻", "偏薄或不明显": "薄白",
}
THICKNESS_ALIAS = {
    "苔覆盖较广": "苔覆盖较广", "苔覆盖较少": "苔覆盖较少",
    "未见明显苔": "苔覆盖较少",
    # 兼容 v1 历史记录里存过的旧值
    "厚苔": "苔覆盖较广", "薄苔": "苔覆盖较少",
}

WATCH = "如果同时出现持续口苦口臭、腹胀、乏力或体重明显下降，建议及时就医，不要仅凭舌象判断。"
DISCLAIMER = "以上为照片观察参考，不构成诊断或治疗建议；身体不适请以医生面诊为准。"


def _quality_note(confidence: float | None) -> str:
    if confidence is None:
        return "照片质量：本次未能评估，建议在自然光下正对镜头重拍一次。"
    pct = round(confidence * 100, 1)
    if confidence >= 0.85:
        return f"照片质量：清晰，识别把握度 {pct}%，本次观察结果可参考。"
    if confidence >= 0.6:
        return f"照片质量：一般（把握度 {pct}%），建议在自然光下、舌头自然伸出时重拍一次。"
    return f"照片质量：偏模糊（把握度 {pct}%），本次结果仅供参考，建议重新拍摄后再观察。"


def _merge_tips(groups: list[list[str]], limit: int = 6) -> list[str]:
    merged: list[str] = []
    for tips in groups:
        for tip in tips or []:
            if tip not in merged:
                merged.append(tip)
    return merged[:limit]


def _constitution_assessment(color_key: str | None, coat_key: str | None,
                             morphology: list[dict]) -> dict:
    """根据可信舌象观察给出用户可读的体质倾向，不输出确定证型。"""
    labels = {item.get("label") for item in morphology}
    evidence: list[str] = []

    # 黄苔与偏红舌同时出现时优先提示饮食、作息相关的湿热倾向。
    if coat_key == "黄苔" and color_key == "红":
        evidence = ["舌色偏红", "黄苔"]
        return {
            "label": "湿热倾向",
            "plain": "舌色偏红、舌苔偏黄，近期可留意饮食偏油辣、饮水不足或作息不规律。",
            "evidence": evidence,
            "tips": ["这几天清淡饮食，少油少辣，多喝水", "尽量规律作息，减少熬夜"],
        }

    if coat_key in {"白苔", "滑苔"}:
        evidence = [coat_key]
        if "齿痕舌" in labels:
            evidence.append("齿痕舌")
        elif "舌体偏胖大" in labels:
            evidence.append("舌体偏胖大")
        return {
            "label": "脾胃湿重倾向",
            "plain": "舌苔偏白或偏湿，舌边有齿痕/舌体偏大，近期可留意消化负担、甜腻饮食和久坐。",
            "evidence": evidence,
            "tips": ["少吃甜食和油腻夜宵，每餐增加蔬菜", "饭后散步 10–15 分钟，避免久坐"],
        }

    if color_key == "红" or "裂纹舌" in labels:
        evidence = ["舌色偏红"] if color_key == "红" else []
        if "裂纹舌" in labels:
            evidence.append("裂纹舌")
        return {
            "label": "偏热倾向",
            "plain": "舌色偏红或舌面有裂纹，近期可留意熬夜、饮水不足和辛辣刺激。",
            "evidence": evidence,
            "tips": ["保证饮水和睡眠，少吃辛辣烧烤", "连续观察 3–5 天变化"],
        }

    if color_key == "淡白" or "舌体偏瘦小" in labels:
        evidence = ["舌色偏淡"] if color_key == "淡白" else []
        if "舌体偏瘦小" in labels:
            evidence.append("舌体偏瘦小")
        return {
            "label": "偏虚/疲劳倾向",
            "plain": "舌色偏淡或舌体偏瘦小，近期可留意饮食摄入、体力和睡眠是否充足。",
            "evidence": evidence,
            "tips": ["三餐规律，每餐安排一份优质蛋白", "避免过度节食和连续熬夜"],
        }

    return {
        "label": "整体较平稳",
        "plain": "当前舌色和舌苔接近常见范围，保持规律饮食和作息即可。",
        "evidence": ["淡红舌", "薄白苔"],
        "tips": ["继续保持清淡、均衡的饮食和规律作息"],
    }


def build_advice(color: str | None, coat: str | None,
                 confidence: float | None = None,
                 thickness: str | None = None,
                 morphology: list[dict] | None = None) -> dict:
    """把舌色 / 苔质 / 厚薄 / 形态观察翻译成通俗解读 + 可执行建议。

    morphology 形如 [{"code": "chihenshe", "label": "齿痕舌", "confidence": 0.62}, ...]
    """
    color_key = COLOR_ALIAS.get((color or "").strip())
    coat_key = COAT_ALIAS.get((coat or "").strip())
    thick_key = THICKNESS_ALIAS.get((thickness or "").strip())
    color_info = COLOR_INFO.get(color_key or "")
    coat_info = COAT_INFO.get(coat_key or "")
    thick_info = THICKNESS_INFO.get(thick_key or "") if thick_key else None

    morph_items = []
    for item in morphology or []:
        label = item.get("label") or item.get("code") or ""
        info = MORPHOLOGY_INFO.get(label)
        if info:
            morph_items.append({
                "label": info["label"],
                "plain": info["plain"],
                "confidence": item.get("confidence"),
                "tips": info.get("tips", []),
            })

    constitution = _constitution_assessment(color_key, coat_key, morph_items)

    parts = []
    if color_info:
        parts.append(f"舌色{color_info['label'].split('（')[0]}")
    if coat_info:
        parts.append(f"舌苔{coat_info['label'].split('（')[0]}")
    if thick_info:
        parts.append(thick_info["label"])
    for item in morph_items:
        parts.append(item["label"])
    summary = "本次观察到：" + " · ".join(parts) if parts else "本次未能得到稳定的舌象观察结果。"

    # 建议合并顺序：苔质（最容易调整）→ 厚薄 → 舌色 → 形态特征
    tips = _merge_tips([
        (coat_info or {}).get("tips", []),
        (thick_info or {}).get("tips", []),
        (color_info or {}).get("tips", []),
        *[item["tips"] for item in morph_items],
    ])

    return {
        "summary": summary,
        "color": {
            "label": color_info["label"] if color_info else (color or "未明确"),
            "plain": color_info["plain"] if color_info else "未能稳定识别舌色，建议重新拍摄观察。",
        },
        "coat": {
            "label": coat_info["label"] if coat_info else (coat or "未明确"),
            "plain": coat_info["plain"] if coat_info else "未能稳定识别舌苔，建议重新拍摄观察。",
        },
        "thickness": {
            "label": thick_info["label"] if thick_info else (thickness or "未判断"),
            "plain": (thick_info or {}).get("plain",
                                            "苔的厚薄由覆盖面积估算（非模型直接输出），仅供参考。"),
        },
        "morphology": morph_items,
        "constitution": constitution,
        "tips": _merge_tips([constitution["tips"], tips]),
        "quality": _quality_note(confidence),
        "watch": WATCH,
        "disclaimer": DISCLAIMER,
    }
