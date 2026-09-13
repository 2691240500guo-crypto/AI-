"""Cross-domain weekly/monthly health report aggregation."""
from __future__ import annotations

from collections import Counter
from datetime import date


def build_health_report(*, period: str, start: date, end: date, assessments: list[dict],
                        meals: list[dict], tongues: list[dict], conversations: int) -> dict:
    calories = sum(float(row.get("calories") or 0) for row in meals)
    protein = sum(float(row.get("protein_g") or 0) for row in meals)
    fat = sum(float(row.get("fat_g") or 0) for row in meals)
    carbs = sum(float(row.get("carbs_g") or 0) for row in meals)
    risks = Counter(row.get("risk_level") or "未分级" for row in assessments)
    latest_tongue = tongues[0] if tongues else {}
    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "assessment": {
            "count": len(assessments),
            "average_score": round(sum(float(row.get("total_score") or 0) for row in assessments) / len(assessments), 2)
            if assessments else 0,
            "risk_distribution": dict(risks),
        },
        "meals": {
            "record_count": len(meals),
            "calories": round(calories, 1),
            "protein_g": round(protein, 1),
            "fat_g": round(fat, 1),
            "carbs_g": round(carbs, 1),
        },
        "tongue": {
            "record_count": len(tongues),
            "latest_color": latest_tongue.get("tongue_color") or "暂无",
            "latest_coat": latest_tongue.get("coat") or "暂无",
        },
        "conversation_count": conversations,
        "highlights": _highlights(assessments, meals, tongues),
        "disclaimer": "本报告仅用于健康趋势观察和生活方式参考，不能替代医生诊断。",
    }


def _highlights(assessments: list[dict], meals: list[dict], tongues: list[dict]) -> list[str]:
    highlights = []
    if any((row.get("risk_level") == "高风险") for row in assessments):
        highlights.append("本周期出现高风险营养测评，建议尽快咨询专业营养师或医生。")
    if meals:
        highlights.append(f"已记录 {len(meals)} 餐饮食，可继续补充完整餐次以提高趋势参考价值。")
    if tongues:
        highlights.append("舌象趋势只作照片观察参考，建议在相近光线和时间下复测。")
    return highlights or ["本周期数据较少，继续记录后可获得更稳定的趋势建议。"]
