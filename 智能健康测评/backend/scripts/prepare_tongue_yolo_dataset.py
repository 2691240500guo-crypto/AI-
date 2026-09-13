"""Convert the Apache-2.0 tongue segmentation dataset into YOLO detection labels.

The source masks describe the tongue silhouette. This script derives one bounding box per mask,
keeps source-provided splits, and can cap each split for a small reproducible demo dataset.
"""
import argparse
import shutil
from pathlib import Path

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Extracted source ourdata directory")
    parser.add_argument("--output", type=Path, default=Path("data/tongue_dataset"))
    parser.add_argument("--train-limit", type=int, default=200)
    parser.add_argument("--val-limit", type=int, default=50)
    parser.add_argument("--test-limit", type=int, default=50)
    return parser.parse_args()


def write_split(source: Path, output: Path, split: str, limit: int) -> int:
    source_split = "val" if split == "val" else split
    image_dir = source / source_split / "images"
    mask_dir = source / source_split / "masks"
    target_images = output / split / "images"
    target_labels = output / split / "labels"
    target_images.mkdir(parents=True, exist_ok=True)
    target_labels.mkdir(parents=True, exist_ok=True)

    count = 0
    for image_path in sorted(image_dir.glob("*")):
        if count >= limit:
            break
        mask_path = mask_dir / image_path.name
        if not mask_path.exists():
            continue
        with Image.open(mask_path).convert("L") as mask:
            bbox = mask.getbbox()
        if not bbox:
            continue
        with Image.open(image_path) as image:
            width, height = image.size
        left, top, right, bottom = bbox
        center_x = (left + right) / 2 / width
        center_y = (top + bottom) / 2 / height
        box_width = (right - left) / width
        box_height = (bottom - top) / height
        if box_width <= 0 or box_height <= 0:
            continue
        shutil.copy2(image_path, target_images / image_path.name)
        (target_labels / f"{image_path.stem}.txt").write_text(
            f"0 {center_x:.6f} {center_y:.6f} {box_width:.6f} {box_height:.6f}\n",
            encoding="ascii",
        )
        count += 1
    return count


def main() -> None:
    args = parse_args()
    generated_dirs = [args.output / split for split in ("train", "val", "test")]
    if any(path.exists() for path in generated_dirs):
        raise RuntimeError(
            f"Refusing to overwrite an existing generated dataset at {args.output}. "
            "Choose an empty output directory."
        )
    counts = {
        "train": write_split(args.source, args.output, "train", args.train_limit),
        "val": write_split(args.source, args.output, "val", args.val_limit),
        "test": write_split(args.source, args.output, "test", args.test_limit),
    }
    if not all(counts.values()):
        raise RuntimeError(f"No usable samples in one or more splits: {counts}")
    print(f"Prepared YOLO dataset: {counts}")


if __name__ == "__main__":
    main()
