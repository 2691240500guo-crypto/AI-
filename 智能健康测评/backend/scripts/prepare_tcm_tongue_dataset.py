"""把 TCM-Tongue（北工商舌象检测数据集）整理成可直接训练的 YOLO 数据集。

数据集来源（公开学术资源）：
  - GitHub: https://github.com/btbuIntelliSense/Intelligent-tongue-diagnosis-detection-dataset
  - Dryad : https://doi.org/10.5061/dryad.1c59zw48r
  论文   : "TCM-Tongue: A Standardized Tongue Image Dataset with Pathological Annotations
           for AI-Assisted TCM Diagnosis"，6,719 张，持证中医师双重审核。

本脚本在体检（2026-09-11 实测）发现的数据问题上做了三件事，**不改动原始数据**：
  1) 补类别名：原始数据没有 classes.txt，按论文顺序内置 id→英文名映射
  2) 裁类别：实例数低于 --min-instances 的类整类剔除（含未定义 id、空类），并重编号
  3) 去泄漏：--drop-leakage 会把与 val/test 内容（MD5）重复的 train 图剔除，
     避免测试集指标虚高（实测有 280 组跨 split 重复）

用法：
    # 只看体检结论，不写文件
    venv/Scripts/python.exe scripts/prepare_tcm_tongue_dataset.py \
        --source data/tcm_tongue_raw --output data/tcm_tongue --dry

    # 正式整理：剔除实例<250 的类 + 去泄漏
    venv/Scripts/python.exe scripts/prepare_tcm_tongue_dataset.py \
        --source data/tcm_tongue_raw --output data/tcm_tongue \
        --min-instances 250 --drop-leakage

    # 云端（AutoDL）：yaml 里写绝对路径，否则会被全局 datasets_dir 劫持
    ... --yaml-path /root/autodl-tmp/tcm_tongue

注意：本数据集是「舌象特征检测」（红舌/白苔/黄苔/齿痕…），不是诊断结论。
      用户侧展示必须标注"仅供健康观察参考，不能替代医疗诊断"。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

SPLITS = ("train", "val", "test")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# 论文/Dryad 描述的类别顺序（0-19）；原始数据缺 classes.txt，用它兜底命名
ID2NAME: dict[int, str] = {
    0: "jiankangshe",    # 健康舌（无异常特征）
    1: "botaishe",       # 剥苔
    2: "hongshe",        # 红舌
    3: "zishe",          # 紫舌（暗红）
    4: "pangdashe",      # 胖大舌
    5: "shoushe",        # 瘦小舌
    6: "hongdianshe",    # 红点舌（点刺）
    7: "liewenshe",      # 裂纹舌
    8: "chihenshe",      # 齿痕舌
    9: "baitaishe",      # 白苔
    10: "huangtaishe",   # 黄苔
    11: "heitaishe",     # 黑苔
    12: "huataishe",     # 滑苔（水滑）
    13: "shenquao",      # 肾区凹陷
    14: "shenqutu",      # 肾区凸起
    15: "gandanao",      # 肝胆区凹陷
    16: "gandantu",      # 肝胆区凸起
    17: "piweiao",       # 脾胃区凹陷
    18: "xinfeitu",      # 心肺区凸起
    19: "xinfeiao",      # 心肺区凹陷
}

NAME2ZH: dict[str, str] = {
    "jiankangshe": "健康舌（无异常特征）",
    "botaishe": "剥苔（苔剥落）",
    "baotaishe": "剥苔（苔剥落）",
    "hongshe": "红舌",
    "zishe": "紫舌（暗红）",
    "pangdashe": "胖大舌",
    "shoushe": "瘦小舌",
    "hongdianshe": "红点舌（点刺）",
    "liewenshe": "裂纹舌",
    "chihenshe": "齿痕舌",
    "baitaishe": "白苔",
    "huangtaishe": "黄苔",
    "heitaishe": "黑苔",
    "huataishe": "滑苔（水滑）",
    "shenquao": "肾区凹陷",
    "shenqutu": "肾区凸起",
    "gandanao": "肝胆区凹陷",
    "gandantu": "肝胆区凸起",
    "piweiao": "脾胃区凹陷",
    "xinfeitu": "心肺区凸起",
    "xinfeiao": "心肺区凹陷",
    "unknown": "未定义类别",
}

# 「特征 → 用户侧结论」规则（可解释、可审计，不引入第二个模型）
COLOR_RULES = [("zishe", "暗红"), ("hongshe", "红")]
COAT_RULES = [("huangtaishe", "黄苔"), ("baitaishe", "白苔")]
COAT_DEFAULT = "薄白（无明显苔色）"
# 「厚苔」无独立标注：用 苔框面积 / 舌体总面积 估算，阈值可调
THICK_COAT_AREA_RATIO = 0.35
# 参与「苔面积占比」计算的类别（最终会与保留类别求交集）
COAT_CLASSES = ("baitaishe", "huangtaishe", "heitaishe", "huataishe")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="整理 TCM-Tongue 为 YOLO 数据集")
    parser.add_argument("--source", type=Path, required=True, help="解压后的数据集根目录")
    parser.add_argument("--output", type=Path, default=Path("data/tcm_tongue"), help="输出目录")
    parser.add_argument("--yaml-path", default=None,
                        help="写进 yaml 的 path（云端填 /root/autodl-tmp/tcm_tongue）；默认用 output")
    parser.add_argument("--min-instances", type=int, default=0,
                        help="实例数低于该值的类别整类剔除（建议 200~250，实测稀有类只有 2~23 个）")
    parser.add_argument("--drop-ids", default="", help="额外强制剔除的类别 id，逗号分隔，如 11,17")
    parser.add_argument("--drop-leakage", action="store_true",
                        help="剔除与 val/test 内容重复的 train 图（防测试集指标虚高）")
    parser.add_argument("--copy", action="store_true", help="复制文件而不是硬链接（跨盘时必须）")
    parser.add_argument("--dry", action="store_true", help="只扫描统计，不写任何文件")
    parser.add_argument("--force", action="store_true", help="允许写入已存在的输出目录")
    return parser.parse_args()


# ---------------- 扫描 ----------------

def find_split_dirs(source: Path) -> dict[str, tuple[Path, Path]]:
    found: dict[str, tuple[Path, Path]] = {}
    for img_dir in sorted(source.rglob("images")):
        if not img_dir.is_dir():
            continue
        split = img_dir.parent.name.lower()
        if split not in SPLITS:
            continue
        for label_name in ("labels", "txt_labels", "annotations_txt"):
            label_dir = img_dir.parent / label_name
            if label_dir.is_dir():
                found[split] = (img_dir, label_dir)
                break
    return found


def read_class_names(source: Path) -> dict[int, str]:
    for candidate in sorted(source.rglob("classes.txt")):
        names = [n.strip() for n in candidate.read_text(encoding="utf-8", errors="ignore").splitlines() if n.strip()]
        if names:
            return {i: n for i, n in enumerate(names)}
    return {}


def read_rows(path: Path) -> list[tuple[int, float, float, float, float]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        f = line.split()
        if len(f) != 5:
            continue
        try:
            cls = int(float(f[0]))
            cx, cy, w, h = (float(v) for v in f[1:])
        except ValueError:
            continue
        if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
            continue
        rows.append((cls, cx, cy, w, h))
    return rows


def md5(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def scan(source: Path) -> dict:
    dirs = find_split_dirs(source)
    if "train" not in dirs:
        raise SystemExit(f"未在 {source} 找到 train/images 与 train/labels，请确认解压路径")
    report: dict = {"source": str(source), "splits": {}, "warnings": [], "dirs": {}}
    for split, (img_dir, label_dir) in dirs.items():
        report["dirs"][split] = str(img_dir)
        images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        ids: Counter[int] = Counter()
        per_image: Counter[int] = Counter()
        missing = orphan = empty = 0
        stems = {p.stem for p in images}
        label_files = sorted(label_dir.glob("*.txt"))
        label_stems = {p.stem for p in label_files}
        missing = len(stems - label_stems)
        orphan = len(label_stems - stems)
        for image_path in images:
            rows = read_rows(label_dir / f"{image_path.stem}.txt")
            per_image[len(rows)] += 1
            if not rows:
                empty += 1
            for cls, *_ in rows:
                ids[cls] += 1
        report["splits"][split] = {
            "images": len(images),
            "labels": len(label_files),
            "instances": sum(ids.values()),
            "missing_label": missing,
            "orphan_label": orphan,
            "empty_label": empty,
            "instances_by_id": dict(sorted(ids.items())),
            "labels_per_image": dict(sorted(per_image.items())),
        }
    return report


def find_leakage(source: Path, dirs: dict[str, tuple[Path, Path]]) -> dict:
    """返回 {train_stem: 重复参照} 与统计。以 val/test 为基准，净化 train。"""
    hashes: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for split, (img_dir, _) in dirs.items():
        for p in sorted(img_dir.iterdir()):
            if p.suffix.lower() in IMAGE_SUFFIXES:
                hashes[md5(p)].append((split, p))
    keep_stems = set()
    dropped: list[str] = []
    groups = 0
    for digest, items in hashes.items():
        if len(items) < 2:
            continue
        splits = {s for s, _ in items}
        if len(splits) < 2:
            continue
        groups += 1
        holds = {s for s in splits if s in ("val", "test")}
        for split, path in items:
            if split == "train" and holds:
                dropped.append(path.name)
            elif split == "train":
                keep_stems.add(path.stem)
    return {
        "groups": groups,
        "dropped_from_train": len(dropped),
        "examples": sorted(dropped)[:8],
        "dropped_names": set(dropped),
    }


# ---------------- 整理 ----------------

def decide_keep(report: dict, args: argparse.Namespace, class_names: dict[int, str]) -> tuple[set[str], dict]:
    """决定保留哪些类别名，并把被剔除的类别与原因记下来。"""
    totals: Counter[int] = Counter()
    for split in report["splits"]:
        for cls_id, count in report["splits"][split]["instances_by_id"].items():
            totals[int(cls_id)] += count
    forced = {int(v) for v in args.drop_ids.replace("，", ",").split(",") if v.strip().isdigit()}
    keep: set[str] = set()
    dropped: list[dict] = []
    for cls_id in sorted(totals):
        name = class_names.get(cls_id) or ID2NAME.get(cls_id) or "unknown"
        count = totals[cls_id]
        if cls_id in forced:
            dropped.append({"id": cls_id, "name": name, "instances": count, "reason": "显式剔除"})
        elif name == "unknown":
            dropped.append({"id": cls_id, "name": name, "instances": count, "reason": "论文未定义的类别 id"})
        elif count < args.min_instances:
            dropped.append({"id": cls_id, "name": name, "instances": count,
                            "reason": f"实例数 {count} < 阈值 {args.min_instances}"})
        else:
            keep.add(name)
    # 论文里定义但数据里一个实例都没有的类（空类）
    for cls_id, name in ID2NAME.items():
        if cls_id not in totals:
            dropped.append({"id": cls_id, "name": name, "instances": 0, "reason": "数据中无实例（空类）"})
    return keep, {"dropped": dropped, "totals": {int(k): v for k, v in totals.items()}}


def materialize(args: argparse.Namespace, dirs: dict[str, tuple[Path, Path]],
                keep: set[str], leakage: dict | None) -> dict:
    output = args.output
    if output.exists() and any(output.iterdir()) and not args.force:
        raise RuntimeError(f"输出目录已存在且非空：{output}（要覆盖请加 --force）")

    keep_names = sorted(keep)
    new_id = {name: idx for idx, name in enumerate(keep_names)}
    dropped_stems = (leakage or {}).get("dropped_names", set())
    written = {split: {"images": 0, "labels": 0, "dropped_leakage": 0,
                       "instances": 0, "empty_after_filter": 0} for split in SPLITS}

    for split, (img_dir, label_dir) in dirs.items():
        for image_path in sorted(img_dir.iterdir()):
            if image_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if split == "train" and image_path.name in dropped_stems:
                written[split]["dropped_leakage"] += 1
                continue
            rows = read_rows(label_dir / f"{image_path.stem}.txt")
            kept_rows = []
            for cls, cx, cy, w, h in rows:
                name = ID2NAME.get(cls, "unknown")
                if name in new_id:
                    kept_rows.append((new_id[name], cx, cy, w, h))
            if not kept_rows:
                written[split]["empty_after_filter"] += 1
                continue
            dst_img = output / split / "images" / image_path.name
            dst_lbl = output / split / "labels" / f"{image_path.stem}.txt"
            dst_lbl.parent.mkdir(parents=True, exist_ok=True)
            for dst, src in ((dst_img, image_path), (dst_lbl, None)):
                if dst.exists():
                    continue
                if src is not None:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    if args.copy:
                        shutil.copy2(src, dst)
                    else:
                        try:
                            os.link(src, dst)
                        except OSError:
                            shutil.copy2(src, dst)
            dst_lbl.write_text(
                "\n".join(f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for c, cx, cy, w, h in kept_rows) + "\n",
                encoding="ascii")
            written[split]["images"] += 1
            written[split]["labels"] += 1
            written[split]["instances"] += len(kept_rows)

    (output / "classes.txt").write_text("\n".join(keep_names) + "\n", encoding="utf-8")
    return written, keep_names


def write_yaml(args: argparse.Namespace, keep_names: list[str]) -> Path:
    # 默认写绝对路径：ultralytics 会用全局 datasets_dir 解析相对 path，
    # 本机该设置指向过别的项目，相对路径会直接 FileNotFoundError。
    target = Path(args.yaml_path) if args.yaml_path else args.output.resolve()
    lines = [f"path: {target.as_posix()}", "train: train/images", "val: val/images",
             "test: test/images", "", "names:"]
    for idx, name in enumerate(keep_names):
        lines.append(f"  {idx}: {name}")
    yaml_path = args.output.parent / f"{args.output.name}.yaml"
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml_path


def main() -> None:
    args = parse_args()
    if not args.source.exists():
        raise SystemExit(f"找不到源目录：{args.source}")

    dirs = find_split_dirs(args.source)
    report = scan(args.source)
    class_names = read_class_names(args.source)
    if not class_names:
        class_names = dict(ID2NAME)
        report["warnings"].append("原始数据没有 classes.txt，已按论文顺序内置 id→英文名映射")

    keep, decision = decide_keep(report, args, class_names)
    totals = decision["totals"]

    leakage = None
    if args.drop_leakage or args.dry:
        leakage = find_leakage(args.source, dirs)
    if args.drop_leakage and leakage["dropped_from_train"] == 0 and leakage["groups"]:
        report["warnings"].append("检测到同 split 内重复图，但无跨 split 重复；train 未剔除任何图")

    summary = {
        "splits": {s: {k: v for k, v in report["splits"][s].items() if k != "instances_by_id"}
                   for s in report["splits"]},
        "total_images": sum(report["splits"][s]["images"] for s in report["splits"]),
        "total_instances": sum(report["splits"][s]["instances"] for s in report["splits"]),
        "class_totals": {f"{cls_id}:{class_names.get(cls_id, 'unknown')}"
                         f"({NAME2ZH.get(class_names.get(cls_id, ''), '')})": v
                         for cls_id, v in sorted(totals.items())},
        "keep_classes": sorted(keep),
        "dropped_classes": decision["dropped"],
        "leakage": leakage and {k: v for k, v in leakage.items() if k != "dropped_names"},
        "color_rules": COLOR_RULES,
        "coat_rules": COAT_RULES,
        "coat_default": COAT_DEFAULT,
        "thick_coat_area_ratio": THICK_COAT_AREA_RATIO,
        "coat_classes": [c for c in COAT_CLASSES if c in keep],
        "warnings": report["warnings"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.dry:
        print("\n[dry] 未写入任何文件。确认无误后去掉 --dry 重跑。")
        return

    written, keep_names = materialize(args, dirs, keep, leakage)
    yaml_path = write_yaml(args, keep_names)
    out = {"written": written, "kept_classes": keep_names, "yaml": str(yaml_path),
           "dropped_classes": decision["dropped"], "leakage": summary["leakage"],
           "class_totals_before": summary["class_totals"],
           "color_rules": COLOR_RULES, "coat_rules": COAT_RULES, "coat_default": COAT_DEFAULT,
           "thick_coat_area_ratio": THICK_COAT_AREA_RATIO,
           "coat_classes": [c for c in COAT_CLASSES if c in keep]}
    stats_path = args.output.parent / "tcm_tongue_stats.json"
    stats_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n保留 {len(keep_names)} 类：{keep_names}")
    print(f"各 split 写入：{written}")
    print(f"训练配置：{yaml_path}")
    print(f"统计报告：{stats_path}")


if __name__ == "__main__":
    main()
