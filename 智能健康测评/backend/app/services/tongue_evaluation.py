"""可复现的舌象模型验收指标。

现有数据集只提供舌体定位标注，因此分类指标必须明确标记为不可评估。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def intersection_over_union(box_a: list[float], box_b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return round(inter / union, 6) if union else 0.0


def detection_metrics(
    predictions: list[tuple[list[float], float]],
    truths: list[list[float]],
    iou_threshold: float = 0.5,
) -> dict[str, float | int]:
    matched: set[int] = set()
    true_positive = 0
    matched_iou_total = 0.0
    for box, _confidence in sorted(predictions, key=lambda item: item[1], reverse=True):
        best_idx = None
        best_iou = iou_threshold
        for index, truth in enumerate(truths):
            if index in matched:
                continue
            score = intersection_over_union(box, truth)
            if score >= best_iou:
                best_idx, best_iou = index, score
        if best_idx is not None:
            matched.add(best_idx)
            true_positive += 1
            matched_iou_total += best_iou
    false_positive = len(predictions) - true_positive
    false_negative = len(truths) - true_positive
    precision = true_positive / (true_positive + false_positive) if predictions else 0.0
    recall = true_positive / (true_positive + false_negative) if truths else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "iou": round(matched_iou_total / true_positive, 4) if true_positive else 0.0,
    }


def classification_evaluation_status(ground_truth_count: int, prediction_count: int) -> dict[str, object]:
    if ground_truth_count <= 0:
        return {
            "status": "not_evaluable",
            "ground_truth_count": 0,
            "prediction_count": prediction_count,
            "reason": "现有舌象数据集没有舌色/苔质真值标注，无法计算分类准确率。",
        }
    return {
        "status": "ready",
        "ground_truth_count": ground_truth_count,
        "prediction_count": prediction_count,
        "reason": "已提供分类真值，可计算 Top-1 准确率。",
    }


def _read_yolo_box(label_path: Path, width: int, height: int) -> list[list[float]]:
    boxes: list[list[float]] = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) != 5:
            continue
        _, cx, cy, w, h = map(float, fields)
        boxes.append([
            (cx - w / 2) * width,
            (cy - h / 2) * height,
            (cx + w / 2) * width,
            (cy + h / 2) * height,
        ])
    return boxes


def evaluate_tongue_dataset(data_root: str | Path, model_path: str | Path, split: str = "test") -> dict:
    """Run a deterministic localization evaluation over a YOLO split."""
    from PIL import Image
    from ultralytics import YOLO

    root = Path(data_root)
    image_dir = root / split / "images"
    label_dir = root / split / "labels"
    model = YOLO(str(model_path))
    aggregate = {"true_positive": 0, "false_positive": 0, "false_negative": 0, "iou_total": 0.0}
    image_count = 0
    for image_path in sorted(image_dir.glob("*")):
        if image_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            continue
        image_count += 1
        with Image.open(image_path) as image:
            width, height = image.size
        result = model.predict(source=str(image_path), conf=0.35, verbose=False, max_det=3)[0]
        boxes = getattr(result, "boxes", None)
        predictions = []
        if boxes is not None:
            for index in range(len(boxes)):
                predictions.append((boxes.xyxy[index].tolist(), float(boxes.conf[index].item())))
        truths = _read_yolo_box(label_dir / f"{image_path.stem}.txt", width, height)
        metrics = detection_metrics(predictions, truths)
        for key in aggregate:
            if key == "iou_total":
                aggregate[key] += float(metrics["iou"]) * int(metrics["true_positive"])
            else:
                aggregate[key] += int(metrics[key])
    tp, fp, fn = aggregate["true_positive"], aggregate["false_positive"], aggregate["false_negative"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "split": split,
        "image_count": image_count,
        "iou_threshold": 0.5,
        "detection": {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "iou": round(aggregate["iou_total"] / tp, 4) if tp else 0.0,
        },
        "classification": classification_evaluation_status(0, image_count),
        "acceptance": {
            "tongue_detection_recall_target": 0.95,
            "tongue_detection_recall_passed": recall >= 0.95,
            "classification_target": 0.85,
            "classification_passed": False,
        },
    }
