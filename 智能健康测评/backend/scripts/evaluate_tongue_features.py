#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""舌象多特征检测 —— 图级（image-level）多标签检出率评估。

为什么不用 mAP：
    mAP 衡量的是「框画得准不准」。而本模块的产品用途是**判断舌象上出现了哪些特征**
    （白苔？黄苔？红舌？），框的精确位置并不影响结论。实测两种口径结论差异很大：
    整体 mAP50 只有 0.39，但"白苔"图级召回可达 0.97。
    因此对外表述与验收一律采用本脚本的图级指标。

口径：
    · 对每张测试图，比较「模型检出的类别集合」与「标注类别集合」
    · 逐个类别累计 TP/FP/FN → 计算 precision / recall / f1（图级）
    · 另给出「标签集合完全一致」的整图准确率

输出：
    eval_out/tongue_imagelevel.json + eval_out/tongue_imagelevel.txt
    同时打印一张按 F1 排序的表，可直接粘进报告 / 答辩材料。

用法：
    # 默认评估 backend/models/tongue/yolov8n-tcm-tongue.pt
    ./venv/Scripts/python.exe scripts/evaluate_tongue_features.py

    # 指定权重与阈值 / 对比两个权重
    ./venv/Scripts/python.exe scripts/evaluate_tongue_features.py --weights a.pt b.pt --conf 0.25

⚠️ 评估用的数据必须与训练数据去重（整理脚本的 --drop-leakage），否则指标虚高。
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from ultralytics import YOLO

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_DS = BACKEND / "data" / "tcm_tongue"
DEFAULT_WEIGHTS = [BACKEND / "models" / "tongue" / "yolov8n-tcm-tongue.pt"]


def load_gt(ds: Path, split: str) -> dict[str, set[int]]:
    gt: dict[str, set[int]] = {}
    for p in sorted((ds / split / "labels").glob("*.txt")):
        ids = set()
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 5:
                ids.add(int(float(parts[0])))
        gt[p.stem] = ids
    return gt


def evaluate(weights: Path, ds: Path, split: str, conf: float, imgsz: int, device: str) -> dict:
    classes = [l.strip() for l in (ds / "classes.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    gt = load_gt(ds, split)
    img_dir = ds / split / "images"
    paths = [str(p) for p in sorted(img_dir.iterdir()) if p.is_file()]

    model = YOLO(str(weights))
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    exact = 0
    n_pred_total = 0
    n = 0

    stream = model.predict(source=paths, imgsz=imgsz, conf=conf, iou=0.5, max_det=20,
                           device=device, stream=True, verbose=False)
    for r in stream:
        stem = Path(r.path).stem
        if stem not in gt:
            continue
        n += 1
        names = r.names if isinstance(r.names, dict) else dict(enumerate(r.names))
        pred = set()
        if r.boxes is not None and len(r.boxes):
            for c in r.boxes.cls.tolist():
                pred.add(names.get(int(c), str(int(c))))
        truth = {classes[i] for i in gt[stem] if i < len(classes)}
        n_pred_total += len(pred)
        if pred == truth:
            exact += 1
        for c in pred & truth:
            tp[c] += 1
        for c in pred - truth:
            fp[c] += 1
        for c in truth - pred:
            fn[c] += 1

    per_class = {}
    for c in classes:
        t, f, m = tp[c], fp[c], fn[c]
        prec = t / (t + f) if (t + f) else 0.0
        rec = t / (t + m) if (t + m) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        per_class[c] = {"tp": t, "fp": f, "fn": m, "support": t + m,
                        "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4)}
    macro = {k: round(sum(v[k] for v in per_class.values()) / max(1, len(classes)), 4)
             for k in ("precision", "recall", "f1")}
    return {
        "weights": str(weights), "split": split, "conf": conf, "imgsz": imgsz,
        "n_images": n, "exact_match": round(exact / n, 4) if n else 0.0,
        "avg_pred_per_image": round(n_pred_total / n, 2) if n else 0.0,
        "macro": macro, "per_class": per_class,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="舌象多特征检测 · 图级多标签检出率评估")
    ap.add_argument("--weights", nargs="+", default=[str(p) for p in DEFAULT_WEIGHTS])
    ap.add_argument("--data", default=str(DEFAULT_DS))
    ap.add_argument("--split", default="test", choices=["train", "val", "test"])
    ap.add_argument("--conf", type=float, default=0.25,
                    help="与线上 TONGUE_YOLO_CONF 保持一致，否则指标与产品行为不符")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default=str(BACKEND / "eval_out"))
    args = ap.parse_args()

    ds = Path(args.data)
    if not (ds / "classes.txt").exists():
        raise SystemExit(f"数据集目录缺少 classes.txt：{ds}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {"conf": args.conf, "split": args.split, "models": {}}
    lines = [f"舌象多特征 · 图级多标签检出率（split={args.split}, conf>={args.conf}, imgsz={args.imgsz}）", ""]

    for w in args.weights:
        wp = Path(w)
        if not wp.exists():
            print(f"[skip] 权重不存在：{wp}")
            continue
        r = evaluate(wp, ds, args.split, args.conf, args.imgsz, args.device)
        tag = wp.stem
        report["models"][tag] = r
        lines.append(f"===== {tag}  ({wp.name}) =====")
        lines.append(f"  测试图 {r['n_images']} 张   标签集合完全一致 {r['exact_match'] * 100:.1f}%   "
                     f"平均每图检出 {r['avg_pred_per_image']} 个特征")
        lines.append(f"  macro  P={r['macro']['precision']}  R={r['macro']['recall']}  F1={r['macro']['f1']}")
        lines.append(f"  {'类别':<14}{'支持数':>7}{'P':>8}{'R':>8}{'F1':>8}  可信度建议")
        for c, v in sorted(r["per_class"].items(), key=lambda kv: -kv[1]["f1"]):
            if v["support"] == 0:
                level = "unusable(测试集无样本)"
            elif v["f1"] >= 0.7:
                level = "high"
            elif v["f1"] >= 0.45:
                level = "medium"
            elif v["recall"] <= 0.1:
                level = "unusable"
            else:
                level = "low"
            lines.append(f"  {c:<14}{v['support']:>7}{v['precision']:>8}{v['recall']:>8}{v['f1']:>8}  {level}")
        lines.append("")
        print(f"{tag}: exact={r['exact_match']:.3f} macroP={r['macro']['precision']} "
              f"macroR={r['macro']['recall']} macroF1={r['macro']['f1']}")

    lines.append("提示：把上表「可信度建议」同步进 app/services/tongue_service.py 的 FEATURE_RELIABILITY，")
    lines.append("      低于 medium 的特征只进检出明细、不写进观察结论。")

    (out_dir / "tongue_imagelevel.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "tongue_imagelevel.txt").write_text("\n".join(lines), encoding="utf-8")
    # CSV 便于贴进报告
    with (out_dir / "tongue_imagelevel.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.writer(fh)
        wr.writerow(["model", "class", "support", "precision", "recall", "f1"])
        for tag, r in report["models"].items():
            for c, v in r["per_class"].items():
                wr.writerow([tag, c, v["support"], v["precision"], v["recall"], v["f1"]])
    print(f"报告已写入：{out_dir / 'tongue_imagelevel.txt'} / .json / .csv")


if __name__ == "__main__":
    main()
