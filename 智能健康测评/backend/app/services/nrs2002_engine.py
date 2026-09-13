"""NRS2002 营养风险筛查：确定性规则评分引擎。

评分标准（0-7 分制，>=3 分为高风险）：
  1. 营养受损程度评分 (0-3)
     - BMI < 18.5（或白蛋白 < 30g/L）                    -> 3 分
     - 近 3 个月体重下降 > 5% / BMI 18.5~20.5 / 进食量 50%~75% -> 1 分
     - 近 2 个月体重下降 > 5% / BMI 18.5~20.5             -> 2 分
     - 体重下降 > 5%/3 个月 或 进食量 25%~50%             -> 1 分
  2. 疾病严重程度评分 (0-3)
     - 一般慢性病（轻度）                                  -> 1 分
     - 需卧床/大手术/肺炎/肿瘤（中度）                      -> 2 分
     - ICU/重症监护（重度）                                -> 3 分
  3. 年龄评分 (0-1)：>= 70 岁 -> 1 分

本实现按课件 2.5/2.6 及 NRS2002 官方标准简化落地，
入参为结构化字段（BMI/体重变化/疾病等级/年龄），输出总分与风险等级。
"""
from dataclasses import dataclass, field
from typing import Dict, Any


# ---------------- 常量：NRS2002 分级规则 ----------------
BMI_SEVERE = 18.5    # BMI < 18.5 营养受损严重
BMI_MILD = 20.5      # BMI < 20.5（18.5~20.5）营养受损轻中度

# 体重下降比例阈值（近 3 个月）
WEIGHT_LOSS_MILD = 5.0      # >5%
WEIGHT_LOSS_SEVERE = 10.0   # >10%（严重）

# 进食量下降程度
DIETARY_LEVELS = {
    "正常": 0.0,
    "减少25%": 0.25,
    "减少50%": 0.5,
    "减少75%": 0.75,
    "几乎不进食": 0.9,
}

# 疾病严重度映射（数值越大越严重）
DISEASE_LEVELS = {
    "无": 0,
    "轻度": 1,   # 一般慢性病（稳定期）
    "中度": 2,   # 需卧床、大手术、肺炎、肿瘤放化疗等
    "重度": 3,   # ICU / 重症监护
}


@dataclass
class NRS2002Result:
    total_score: int
    nutritional_score: int        # 营养受损分 0-3
    disease_score: int            # 疾病严重度分 0-3
    age_score: int                # 年龄分 0-1
    risk_level: str               # 无风险/低风险/中风险/高风险
    basis: str                    # 评分依据（中文说明）
    recommendations: str = ""     # 建议（规则模板生成，LLM 会再增强）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_score": self.total_score,
            "nutritional_score": self.nutritional_score,
            "disease_score": self.disease_score,
            "age_score": self.age_score,
            "risk_level": self.risk_level,
            "basis": self.basis,
            "recommendations": self.recommendations,
        }


def _score_nutritional(bmi: float | None,
                       weight_loss_pct: float | None,
                       dietary_intake: str | None) -> tuple[int, str]:
    """营养受损程度评分 0-3 分。

    依据（NRS2002）：
      - BMI < 18.5                          -> 3 分（严重受损）
      - 3 个月内体重下降 > 5% 或进食量 25%~50% -> 1 分
      - 2 个月内体重下降 > 5% 或 BMI 18.5~20.5 -> 2 分
    说明：课件与临床简化版常用「体重下降 + BMI」组合判定，
    这里按「取最高档」实现，保证 >=3 分判高风险的标准不被绕过。
    """
    reasons = []
    score = 0

    # 1) BMI 维度（对齐课件 D5 示例分档：<18.5→3分；18.5~20.5→1分）
    if bmi is not None:
        if bmi < BMI_SEVERE:
            score = max(score, 3)
            reasons.append(f"BMI {bmi:.1f}＜18.5 → 3 分")
        elif bmi < BMI_MILD:
            score = max(score, 1)
            reasons.append(f"BMI {bmi:.1f}（18.5-20.5）→ 1 分")

    # 2) 体重下降维度（近 3 个月比例）
    if weight_loss_pct is not None:
        if weight_loss_pct > 10:
            score = max(score, 2)
            reasons.append(f"近3个月体重下降 {weight_loss_pct:.1f}%（＞10%）→ 2 分")
        elif weight_loss_pct > WEIGHT_LOSS_MILD:
            score = max(score, 1)
            reasons.append(f"近3个月体重下降 {weight_loss_pct:.1f}%（＞5%）→ 1 分")

    # 3) 进食量维度
    if dietary_intake:
        level = DIETARY_LEVELS.get(dietary_intake)
        if level is not None and level >= 0.75:
            score = max(score, 3)
            reasons.append(f"进食量{dietary_intake}（严重不足）→ 3 分")
        elif level is not None and level >= 0.5:
            score = max(score, 1)
            reasons.append(f"进食量{dietary_intake} → 1 分")

    if score == 0:
        reasons.append("营养状况正常（BMI≥20.5，体重稳定）→ 0 分")
    return min(score, 3), "；".join(reasons)


def _score_disease(disease_level: str) -> tuple[int, str]:
    """疾病严重程度评分 0-3 分"""
    key = (disease_level or "无").strip()
    # 支持中文与常见别名
    alias = {
        "一般慢性病": "轻度", "慢性病稳定期": "轻度", "高血压": "轻度",
        "糖尿病": "轻度", "轻度": "轻度", "1": "轻度",
        "需卧床": "中度", "大手术": "中度", "肺炎": "中度",
        "肿瘤": "中度", "放化疗": "中度", "中度": "中度", "2": "中度",
        "icu": "重度", "ICU": "重度", "重症监护": "重度",
        "重症": "重度", "重度": "重度", "3": "重度",
    }
    norm = alias.get(key, "无")
    score = DISEASE_LEVELS.get(norm, 0)
    desc = {
        "无": "无相关疾病 → 0 分",
        "轻度": "轻度疾病（一般慢性病稳定期）→ 1 分",
        "中度": "中度疾病（需卧床/大手术/肺炎/肿瘤）→ 2 分",
        "重度": "重度疾病（ICU/重症监护）→ 3 分",
    }[norm]
    return score, desc


def _score_age(age: float | None) -> tuple[int, str]:
    """年龄评分 0-1 分：>=70 岁 -> 1 分"""
    if age is not None and age >= 70:
        return 1, "年龄 ≥70 岁 → 1 分"
    return 0, "年龄 <70 岁 → 0 分"


def evaluate_nrs2002(
    bmi: float | None = None,
    weight_loss_pct: float | None = None,
    disease_level: str = "无",
    dietary_intake: str | None = None,
    age: int | None = None,
) -> NRS2002Result:
    """NRS2002 营养风险筛查主入口。

    Args:
        bmi: 体质指数
        weight_loss_pct: 近3个月体重下降百分比（如 5.0 表示 5%）
        disease_level: 疾病严重度（无/轻度/中度/重度 或 别名）
        dietary_intake: 进食情况（正常/减少25%/减少50%/减少75%/几乎不进食）
        age: 年龄（岁）
    """
    nut_score, nut_basis = _score_nutritional(bmi, weight_loss_pct, dietary_intake)
    dis_score, dis_basis = _score_disease(disease_level)
    age_score, age_basis = _score_age(age)

    total = nut_score + dis_score + age_score
    # NRS2002 核心判据：总分 >= 3 存在营养风险（需营养支持）
    # 细分档位（供可视化/报告使用）：0 无 / 1 低 / 2 中 / >=3 高
    if total >= 3:
        risk = "高风险"
    elif total == 2:
        risk = "中风险"
    elif total == 1:
        risk = "低风险"
    else:
        risk = "无风险"

    basis = f"1.营养受损：{nut_basis}；2.疾病严重度：{dis_basis}；3.年龄：{age_basis}；总分={nut_score}+{dis_score}+{age_score}={total}分"

    rec = _rule_recommendation(total, risk)
    return NRS2002Result(
        total_score=total,
        nutritional_score=nut_score,
        disease_score=dis_score,
        age_score=age_score,
        risk_level=risk,
        basis=basis,
        recommendations=rec,
    )


def _rule_recommendation(total: int, risk: str) -> str:
    """规则模板生成的基础建议（LLM 增强前的兜底）"""
    if total >= 3:
        return (
            "建议立即进行营养干预：① 优先就诊临床营养科，评估是否需要肠内/肠外营养支持；"
            "② 高蛋白高能量饮食，每日记录体重变化；③ 治疗原发疾病，动态复查营养指标（白蛋白、前白蛋白）。"
        )
    if total >= 1:
        return (
            "存在营养风险倾向：① 增加优质蛋白摄入（鱼、蛋、奶、豆制品）；"
            "② 少食多餐，保证能量充足；③ 每周监测体重，2-4 周后复评。"
        )
    return (
        "目前营养状况良好：保持均衡饮食，食物多样，适量运动，"
        "每年定期进行营养风险筛查即可。"
    )
