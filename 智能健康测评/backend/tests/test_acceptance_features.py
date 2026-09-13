from datetime import date, datetime
from types import SimpleNamespace

from app.services.moderation_service import moderation_verdict_for_unavailable
from app.services.report_service import build_health_report
from app.services.tongue_evaluation import (
    classification_evaluation_status,
    detection_metrics,
    intersection_over_union,
)
from app.services.tongue_advice import build_advice
from app.services.tongue_service import serialize_tongue


def test_tongue_iou_and_detection_metrics_are_reportable():
    assert intersection_over_union([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    metrics = detection_metrics(
        predictions=[([0, 0, 10, 10], 0.9)],
        truths=[[0, 0, 10, 10]],
        iou_threshold=0.5,
    )
    assert metrics == {
        "true_positive": 1,
        "false_positive": 0,
        "false_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "iou": 1.0,
    }


def test_tongue_classification_reports_missing_ground_truth_instead_of_accuracy():
    result = classification_evaluation_status(ground_truth_count=0, prediction_count=10)
    assert result["status"] == "not_evaluable"
    assert "真值" in result["reason"]


def test_tongue_advice_explains_yellow_coat_as_a_simple_damp_heat_tendency():
    advice = build_advice("红", "黄苔", confidence=0.82)

    assert advice["constitution"]["label"] == "湿热倾向"
    assert "舌苔偏黄" in advice["constitution"]["plain"]
    assert advice["constitution"]["evidence"] == ["舌色偏红", "黄苔"]


def test_tongue_advice_uses_shape_evidence_for_spleen_stomach_tendency():
    advice = build_advice(
        "淡红",
        "白苔",
        confidence=0.76,
        morphology=[{"label": "齿痕舌", "confidence": 0.61}],
    )

    assert advice["constitution"]["label"] == "脾胃湿重倾向"
    assert "舌边有齿痕" in advice["constitution"]["plain"]
    assert advice["constitution"]["evidence"] == ["白苔", "齿痕舌"]


def test_tongue_advice_marks_common_color_and_coat_as_stable_reference():
    advice = build_advice("淡红", "薄白", confidence=0.9)

    assert advice["constitution"]["label"] == "整体较平稳"
    assert "常见范围" in advice["constitution"]["plain"]


def test_serialized_tongue_record_keeps_coat_type_and_constitution_tendency():
    record = SimpleNamespace(
        id=7,
        user_id="user",
        status="detected",
        tongue_color="红",
        coat="黄苔·苔覆盖较广（约 82%）",
        confidence=0.82,
        box=[1, 2, 30, 40],
        image_url="",
        image_object_name="",
        note="",
        detail={
            "advice": {
                "constitution": {
                    "label": "湿热倾向",
                    "plain": "舌苔偏黄，近期可留意饮食和作息。",
                }
            }
        },
        created_at=None,
    )

    result = serialize_tongue(record)

    assert result["coat_type"] == "黄苔"
    assert result["constitution"]["label"] == "湿热倾向"


def test_unavailable_image_moderation_is_not_safe_to_publish():
    verdict = moderation_verdict_for_unavailable("vision timeout")
    assert verdict["checked"] is False
    assert verdict["safe"] is False
    assert verdict["status"] == "pending_review"


def test_health_report_contains_period_and_cross_domain_totals():
    report = build_health_report(
        period="week",
        start=date(2026, 9, 4),
        end=date(2026, 9, 10),
        assessments=[{"total_score": 3, "risk_level": "高风险"}],
        meals=[{"calories": 600, "protein_g": 30, "fat_g": 20, "carbs_g": 70}],
        tongues=[{"tongue_color": "偏红", "coat": "偏厚"}],
        conversations=4,
    )
    assert report["period"] == "week"
    assert report["assessment"]["count"] == 1
    assert report["meals"]["calories"] == 600.0
    assert report["tongue"]["latest_color"] == "偏红"
    assert report["conversation_count"] == 4
