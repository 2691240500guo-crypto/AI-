"""Train the F9 3+3 tongue observation classifier.

The current public locator corpus has no colour/coating annotations. This script therefore
creates transparent weak labels from ROI colour statistics, trains a reproducible multitask
checkpoint, and records that limitation in the model card. Replace the labels with clinician
annotations before clinical use.
"""

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from app.services.tongue_classifier import TongueMultiHeadClassifier


def weak_labels(image: Image.Image) -> tuple[int, int]:
    pixels = list(image.convert("RGB").resize((32, 32)).getdata())
    r = sum(p[0] for p in pixels) / len(pixels)
    g = sum(p[1] for p in pixels) / len(pixels)
    b = sum(p[2] for p in pixels) / len(pixels)
    color = 2 if r > g * 1.25 and r > b * 1.35 else 1 if r > g * 1.08 and r > b * 1.15 else 0
    brightness = (r + g + b) / 3
    coat = 2 if r > b * 1.2 and g > b * 1.1 else 1 if brightness < 128 else 0
    return color, coat


class TongueDataset(Dataset):
    def __init__(self, root: Path, split: str):
        self.root = root
        self.items = sorted((root / split / "images").glob("*"))
        self.transform = transforms.Compose([transforms.Resize((128, 128)), transforms.ToTensor()])

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        image = Image.open(self.items[index]).convert("RGB")
        label_path = self.root / "train" / "labels" / f"{self.items[index].stem}.txt"
        if label_path.exists():
            try:
                values = [float(v) for v in label_path.read_text(encoding="utf-8").splitlines()[0].split()]
                _, cx, cy, width, height = values
                left = max(0, int((cx - width / 2) * image.width))
                top = max(0, int((cy - height / 2) * image.height))
                right = min(image.width, int((cx + width / 2) * image.width))
                bottom = min(image.height, int((cy + height / 2) * image.height))
                if right > left and bottom > top:
                    image = image.crop((left, top, right, bottom))
            except (ValueError, IndexError):
                pass
        color, coat = weak_labels(image)
        return self.transform(image), torch.tensor(color), torch.tensor(coat)


def train(data_root: Path, output: Path, epochs: int = 5):
    torch.manual_seed(42)
    dataset = TongueDataset(data_root, "train")
    if not dataset:
        raise SystemExit("No training images found")
    loader = DataLoader(dataset, batch_size=32, shuffle=True, num_workers=0)
    model = TongueMultiHeadClassifier()
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    model.train()
    for _ in range(epochs):
        for images, colors, coats in loader:
            color_logits, coat_logits = model(images)
            loss = loss_fn(color_logits, colors) + loss_fn(coat_logits, coats)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": {
        "tongue_color": ["淡白", "淡红", "红"],
        "coat": ["薄白", "厚腻", "黄腻"],
        "label_source": "weak colour statistics from public locator corpus",
    }}, output)
    print(f"saved {output} ({len(dataset)} images)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data/tongue_dataset"))
    parser.add_argument("--output", type=Path, default=Path("models/tongue/tongue_classifier.pt"))
    parser.add_argument("--epochs", type=int, default=5)
    args = parser.parse_args()
    train(args.data_root, args.output, args.epochs)
