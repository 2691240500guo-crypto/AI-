"""Print the tongue localization acceptance report as JSON."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.tongue_evaluation import evaluate_tongue_dataset


report = evaluate_tongue_dataset(
    ROOT / "data" / "tongue_dataset",
    ROOT / "models" / "tongue" / "yolov8n-tongue.pt",
    split="test",
)
print(json.dumps(report, ensure_ascii=False, indent=2))
