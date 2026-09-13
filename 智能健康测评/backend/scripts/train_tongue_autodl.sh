#!/usr/bin/env bash
# ============================================================================
# 在 AutoDL GPU 实例上一条命令跑完舌象多特征检测训练（14 类）
#
# 前置（本地做完再上传，见 docs/舌象多特征检测_数据下载与云端训练手册.md）：
#   1. 本地已跑过整理：backend/data/tcm_tongue（含 train/val/test + classes.txt）
#   2. 把该目录压成 zip 上传到 /root/autodl-tmp/tcm_tongue.zip
#   3. 上传 backend/scripts/ 到 /root/autodl-tmp/project/backend/scripts/
#
# 用法（建议在 tmux 里跑）：
#   tmux new -s t
#   cd /root/autodl-tmp/project/backend
#   bash scripts/train_tongue_autodl.sh
#   EPOCHS=50 BATCH=16 bash scripts/train_tongue_autodl.sh    # 想更快
#
# 也支持直接上传原始下载包（脚本会自动现场整理）：
#   DATA_ZIP=/root/autodl-tmp/tcm_tongue_raw.zip bash scripts/train_tongue_autodl.sh
#
# ⚠️ 若报 `$'\r': command not found`：Windows 上传带了 CRLF，先执行
#    sed -i 's/\r$//' scripts/train_tongue_autodl.sh
# ============================================================================
set -euo pipefail

# ---- AutoDL 环境适配：非交互 SSH 下 PATH 里没有 conda，python/pip 都找不到 ----
if ! command -v python >/dev/null 2>&1; then
  for _p in /root/miniconda3/bin /opt/conda/bin /usr/local/bin; do
    if [ -x "$_p/python" ]; then export PATH="$_p:$PATH"; break; fi
  done
fi
command -v python >/dev/null 2>&1 || { echo "!! 找不到 python，请确认镜像类型"; exit 1; }
echo "python: $(command -v python)  $($(command -v python) -V 2>&1 | head -1)"

# 自动切到 backend/ 目录：脚本内的 scripts/xxx 相对路径依赖它
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
echo "工作目录：$(pwd)"

DATA_ZIP="${DATA_ZIP:-/root/autodl-tmp/tcm_tongue.zip}"
WORK=/root/autodl-tmp
DS="$WORK/tcm_tongue"
YAML="$WORK/tcm_tongue.yaml"

EPOCHS="${EPOCHS:-150}"
IMGSZ="${IMGSZ:-640}"
BATCH="${BATCH:-32}"
DEVICE="${DEVICE:-0}"
BASE="${BASE:-yolov8n.pt}"
NAME="${NAME:-tcm-tongue-v2}"     # 与 v1 分开命名：ultralytics 的 exist_ok=false 不允许同名目录，且便于对比两版
PROJECT="$WORK/runs"

# ---- 舌象专用增强（v2）----
# 首轮实测（默认增强）mAP50 仅 0.388，逐类呈「框越大越准」：白苔 0.95 / 黄苔 0.84
# vs 红点舌 0.014 / 滑苔 0.002。主因是 mosaic（四图拼接）与 erasing（随机遮挡）
# 破坏了「整舌级」标注的语义，scale 过大又让小目标消失。
MOSAIC="${MOSAIC:-0.0}"          # 关：整舌特征不能被拼图裁切
ERASING="${ERASING:-0.0}"        # 关：不要把舌面挖掉一块
SCALE="${SCALE:-0.25}"           # 原 0.5 太大
TRANSLATE="${TRANSLATE:-0.05}"   # 原 0.1
FLIPLR="${FLIPLR:-0.0}"          # 舌象左右翻转无临床意义
CLS_GAIN="${CLS_GAIN:-1.0}"      # 原 0.5，14 类多标签任务需要更高分类权重
HSV_S="${HSV_S:-0.3}"            # 原 0.7，舌色是核心特征，颜色扰动不能太狠
HSV_V="${HSV_V:-0.3}"            # 原 0.4

hr() { printf '%s\n' "------------------------------------------------------------"; }

hr
echo "[0/5] 环境自检"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || echo "!! 未检测到 GPU"
python -c "import torch; print('torch', torch.__version__, '| cuda available:', torch.cuda.is_available())"
df -h "$WORK" | tail -1
if ! python -c "import ultralytics" >/dev/null 2>&1; then
  echo "安装 ultralytics（首次约 1~3 分钟）…"
  # 不要加 -q：静默模式下卡住时完全看不到进度，也无法触发下面的 fallback。
  # 显式用清华源：本机 /etc/pip.conf 默认指向阿里云源，实测会长时间悬挂（8 分钟无进展）。
  python -m pip install --timeout 60 --retries 2 --progress-bar off \
      -i https://pypi.tuna.tsinghua.edu.cn/simple ultralytics 2>&1 | tail -8 \
    || python -m pip install --timeout 60 --retries 2 --progress-bar off ultralytics 2>&1 | tail -8 \
    || {
      echo "pip 直连失败，改用 AutoDL 学术加速重试 …"
      # shellcheck disable=SC1091
      source /etc/network_turbo 2>/dev/null || true
      python -m pip install --timeout 60 --progress-bar off ultralytics
    }
fi
python -c "import ultralytics; print('ultralytics', ultralytics.__version__)"

hr
echo "[1/5] 准备数据集"
if [ -d "$DS/train/images" ] && [ -n "$(ls -A "$DS/train/images" 2>/dev/null)" ]; then
  echo "数据集已就绪，跳过解压：$DS"
else
  [ -f "$DATA_ZIP" ] || { echo "!! 找不到压缩包：$DATA_ZIP"; exit 1; }
  mkdir -p "$WORK/_unzip"
  echo "解压中（约 1 GB，视磁盘速度 1~3 分钟）…"
  unzip -q -o "$DATA_ZIP" -d "$WORK/_unzip"

  # 自动判断是「已整理版」还是「原始下载版」——判据是 classes.txt 是否存在
  SRC="$(dirname "$(find "$WORK/_unzip" -name classes.txt -print -quit 2>/dev/null)" 2>/dev/null)"
  if [ -n "$SRC" ] && [ -f "$SRC/classes.txt" ] && [ -d "$SRC/train/images" ]; then
    # A) 已整理版：直接搬到数据盘，**不要再跑一遍裁类**（会把 244 实例的 zishe 误剔）
    mkdir -p "$DS"
    cp -r "$SRC/." "$DS/"
    echo "已就绪（整理版，含 $(wc -l < "$DS/classes.txt") 类）：$DS"
  else
    # B) 原始下载数据：现场整理（裁类 200 + 去泄漏）
    # 阈值取 200 而非 250：zishe（紫舌/暗红）只有 252 个实例，离 250 太近容易被误剔
    echo "未发现 classes.txt，按原始数据现场整理（裁类 200 + 去泄漏）…"
    python scripts/prepare_tcm_tongue_dataset.py \
        --source "$WORK/_unzip" --output "$DS" \
        --min-instances 200 --drop-leakage --force
  fi
fi

# 无论数据来源，yaml 一律重写：本地 yaml 里存的是本地绝对路径，云端必须指向 /root/autodl-tmp
python - "$DS" "$YAML" <<'PY'
import pathlib, sys
ds, yaml_path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
classes = [l.strip() for l in (ds / "classes.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
if not classes:
    raise SystemExit("!! 数据集缺少 classes.txt")
lines = [f"path: {ds.as_posix()}", "train: train/images", "val: val/images",
         "test: test/images", "", "names:"]
lines += [f"  {i}: {name}" for i, name in enumerate(classes)]
yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"yaml 已生成：{yaml_path}（{len(classes)} 类）")
PY

echo "数据集规模：$(python - "$DS" <<'PY'
import pathlib, sys
ds = pathlib.Path(sys.argv[1])
for split in ("train", "val", "test"):
    imgs = list((ds / split / "images").glob("*")) if (ds / split / "images").exists() else []
    lbls = list((ds / split / "labels").glob("*.txt")) if (ds / split / "labels").exists() else []
    print(f"{split}: {len(imgs)} 图 / {len(lbls)} 标签", end="   ")
print()
PY
)"

hr
# 基座权重本地化：国内机器从 GitHub 拉 yolov8n.pt 经常失败，优先用已上传的本地副本
if [ "$BASE" = "yolov8n.pt" ] && [ -f "$WORK/yolov8n.pt" ]; then
  BASE="$WORK/yolov8n.pt"
  echo "使用本地基座权重（免联网下载）：$BASE"
fi
echo "[2/5] 开始训练：$BASE   epochs=$EPOCHS imgsz=$IMGSZ batch=$BATCH device=$DEVICE"
echo "      增强：mosaic=$MOSAIC erasing=$ERASING scale=$SCALE translate=$TRANSLATE fliplr=$FLIPLR cls=$CLS_GAIN hsv_s=$HSV_S hsv_v=$HSV_V"
python scripts/train_tongue_yolo.py \
    --data "$YAML" --base "$BASE" --epochs "$EPOCHS" --imgsz "$IMGSZ" \
    --batch "$BATCH" --device "$DEVICE" --project "$PROJECT" --name "$NAME" \
    --mosaic "$MOSAIC" --erasing "$ERASING" --scale "$SCALE" \
    --translate "$TRANSLATE" --fliplr "$FLIPLR" --cls "$CLS_GAIN" \
    --hsv-s "$HSV_S" --hsv-v "$HSV_V"

BEST="$PROJECT/$NAME/weights/best.pt"
[ -f "$BEST" ] || { echo "!! 训练未产出 best.pt"; exit 1; }

hr
echo "[3/5] test 集验收评估（含逐类指标）"
python - "$BEST" "$YAML" "$IMGSZ" "$DEVICE" <<'PY'
import json, sys
from pathlib import Path
from ultralytics import YOLO

best, yaml_path, imgsz, device = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
model = YOLO(best)
metrics = model.val(data=yaml_path, split="test", imgsz=imgsz, device=device,
                    plots=True, verbose=False)
out = {
    "weights": best,
    "precision": round(float(metrics.box.mp), 4),
    "recall": round(float(metrics.box.mr), 4),
    "mAP50": round(float(metrics.box.map50), 4),
    "mAP50_95": round(float(metrics.box.map), 4),
    "per_class_mAP50": {},
}
names = model.names if isinstance(model.names, dict) else dict(enumerate(model.names))
for idx, ap in zip(metrics.box.ap_class_index, metrics.box.ap50):
    key = names.get(int(idx), str(idx))
    out["per_class_mAP50"][key] = round(float(ap), 4)
report = Path("/root/autodl-tmp/tcm_tongue_eval.json")
report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"precision {out['precision']}  recall {out['recall']}  "
      f"mAP50 {out['mAP50']}  mAP50-95 {out['mAP50_95']}")
print("逐类 mAP50（低于 0.5 的类别样本可能不足）：")
for key, value in sorted(out["per_class_mAP50"].items(), key=lambda kv: kv[1]):
    flag = "  <-- 偏弱" if value < 0.5 else ""
    print(f"  {key:<16} {value}{flag}")
print(f"评估报告已写入：{report}")
PY

hr
echo "[4/5] 训练产物"
ls -lh "$BEST"
ls -lh "$PROJECT/$NAME" | head -20

hr
echo "[5/5] 下一步：把权重下载回本地"
cat <<EOF
best.pt 在云端路径：
  $BEST

在你自己的电脑上执行（换成实例页面的端口与域名）：
  scp -P <端口> root@<主机>.autodl.com:$BEST  ./yolov8n-tcm-tongue.pt

然后放回项目：
  backend/models/tongue/yolov8n-tcm-tongue.pt
  （先备份原来的 yolov8n-tongue.pt，别直接覆盖）

⚠️ 训练完立刻在 AutoDL 控制台【关机】；彻底不用了再【释放】。
   关机不收 GPU 费，但仍按天收少量数据盘费。
EOF
hr
echo "训练脚本执行完毕。"
