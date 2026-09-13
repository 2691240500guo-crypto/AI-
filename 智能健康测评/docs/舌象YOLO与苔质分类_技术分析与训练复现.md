# 舌象 YOLO 定位 + 舌色/苔质分类：技术链路、训练步骤与实测复现

> 模块代号 **F9**（舌体定位、舌色与苔质分类）。本文回答三件事：**怎么做的**、**怎么训练/复现的**、**实际水平如何（含实测诊断出的问题）**。
> 所有指标均在 2026-09-11 于本机复现，命令与输出可原地重跑。

---

## 0. 一句话结论

| 环节 | 实现 | 实测水平 |
|---|---|---|
| 舌体定位（YOLOv8n，单类 `tongue`） | ✅ 真训练、真权重 | **P 0.999 / R 1.000 / mAP50 0.995 / mAP50-95 0.875**（50 张独立 test） |
| 舌色分类（3 类） | ⚠️ 弱标签演示构建 | **退化为常量输出**：训练标签 200/200 全「红」→ 模型 50/50 全「红」 |
| 苔质分类（3 类） | ⚠️ 弱标签演示构建 | **≈ 多数类猜测**：50/50 全「黄腻」，平均置信度 0.447（随机基线 0.333） |
| 分类准确率 | ❌ 无法评估 | 数据集**没有舌色/苔质真值**，验收标准 0.85 标记为 `not_evaluable` |

**答辩口径**：可以讲"YOLO 舌体定位 + 多任务分类头的工程闭环"，**不能**讲"舌苔识别准确率"。分类头的真实状态是"弱标签跑通了训练/推理/落库全链路"，不是"具备识别能力"。

---

## 1. 整体链路

```
用户上传舌象照片
      │
      ▼
[前端] TonguePage.vue  pick() → preview()
      │  POST /api/tongue/analyze   (需健康数据授权，否则 428)
      ▼
[服务] tongue_service.analyze_tongue(image_bytes, mime)
      │
      ├─ _get_model()      → YOLOv8n(tongue) 惰性加载，进程内缓存
      │      └─ 权重缺失 → 自动降级「整图规则观察」demo 模式（status=demo）
      ├─ model.predict(conf=0.35, max_det=3, verbose=False)
      │      └─ 无框 → status=not_detected（不落库）
      ├─ _observe_roi(image, box)   ← 逐个检测框裁剪 ROI
      │      ├─ 颜色统计规则（始终计算，作为兜底观察）
      │      └─ _get_classifier() → TongueMultiHeadClassifier（分类头优先）
      │            失败 → 回退规则观察，打 warning，不打断主链路
      └─ build_advice(色, 苔, 置信度) → 通俗解读 + 3~6 条生活建议 + 照片质量提示
      │
      ▼
[前端] canvas 画检测框 + 置信度标签 → 结果卡（色/苔/建议/质量提示）
      │  POST /api/tongue/save
      ▼
[落库] TongueRecord：原图加密存 MinIO 私有桶 → 记录 box/detail 加密列
      │  GET /api/tongue/records · GET /api/tongue/images/{id}（带 Token 网关解密）
      ▼
[前端] 历史趋势时间轴（舌色圆点 + 与上次对比文案）
```

---

## 2. 数据来源与准备

### 2.1 来源（Apache-2.0，可商用可改造）

`backend/data/tongue_dataset/SOURCE.md` 记录：

| 项 | 值 |
|---|---|
| 上游仓库 | `224224ybyy/Tongue-Image-Segmentation-Dataset`（GitHub，2026-09-10 拉取） |
| 原始文件 | `ourdata.zip` |
| SHA-256 | `a9a166af666207ee9db313d567b14089b4ac9c53278dc5d5e080144249554a1c` |
| 许可 | Apache-2.0 |
| 原始标注 | **分割掩码**（描述舌体轮廓），**无舌色/苔质标注** |

### 2.2 掩码 → 检测框转换（`scripts/prepare_tongue_yolo_dataset.py`）

脚本只做一件事：**用 `PIL.Image.getbbox()` 从分割掩码算出舌体的最小外接矩形**，写成 YOLO 单类标签。

```python
with Image.open(mask_path).convert("L") as mask:
    bbox = mask.getbbox()            # 掩码非零像素的最小外接矩形
left, top, right, bottom = bbox
center_x = (left + right) / 2 / width
center_y = (top + bottom) / 2 / height
box_width  = (right - left) / width
box_height = (bottom - top) / height
# 写 labels/<stem>.txt → "0 cx cy w h"（归一化，类 id 恒为 0）
```

关键设计：

- **保留上游 split**（train/val/test 不重新洗牌），保证可复现；
- **各 split 限量**（`--train-limit 200 / --val-limit 50 / --test-limit 50`）做成小体量演示集；
- **拒绝覆盖已生成目录**（`RuntimeError: Refusing to overwrite...`），防误删；
- 任一 split 为空直接报错，避免"静默生成半个数据集"。

命令：

```bash
cd "D:/项目阶段/项目实操/智能健康测评/backend"
./venv/Scripts/python.exe scripts/prepare_tongue_yolo_dataset.py \
    --source <解压后的 ourdata 目录> \
    --output data/tongue_dataset \
    --train-limit 200 --val-limit 50 --test-limit 50
```

产物（实测）：`train 200/200`、`val 50/50`、`test 50/50`（images/labels 一一对应），测试图平均 ~55 KB。

### 2.3 数据集配置

`backend/data/tongue.yaml`：

```yaml
path: data/tongue_dataset      # ⚠️ 相对路径，见 7.1 的复现坑
train: train/images
val: val/images
test: test/images
names:
  0: tongue
```

---

## 3. YOLO 舌体定位训练

### 3.1 训练脚本（`scripts/train_tongue_yolo.py`，28 行，薄封装）

```python
model = YOLO(args.base)          # 默认 yolov8n.pt（COCO 预训练）
model.train(
    data=args.data, epochs=args.epochs, imgsz=args.imgsz,
    project=args.project, name=args.name, batch=args.batch,
    # 可选 device
)
```

默认参数：`--epochs 80 --imgsz 640 --batch 16`，但**实际 demo 训练用的是更小的配置**（CPU 上的取舍，见下）。

### 3.2 实际训练命令（来自 `MODEL_CARD.md` 与 `runs/tongue/demo-locator/args.yaml`）

```bash
./venv/Scripts/python.exe scripts/train_tongue_yolo.py \
    --data data/tongue.yaml --epochs 8 --imgsz 256 --batch 16 \
    --device cpu --project runs/tongue --name demo-locator
```

| 训练配置 | 值 | 说明 |
|---|---|---|
| 基座权重 | `yolov8n.pt`（Ultralytics v8.4.0 release） | 迁移学习，8 类→单类 `tongue` |
| epochs / imgsz / batch | 8 / 256 / 16 | CPU 环境，256px 已足够（舌体占图比例大） |
| device | cpu | 无 GPU |
| 优化器 | `auto`（Ultralytics 自选，lr0 0.01 / lrf 0.01 / momentum 0.937 / wd 0.0005） | 见 args.yaml |
| 增强 | mosaic 1.0、hsv_s 0.7、hsv_v 0.4、scale 0.5、translate 0.1、fliplr 0.5、erasing 0.4、randaugment | Ultralytics 默认增强 |
| amp / deterministic | true / true | 混合精度 + 确定性种子（seed=0） |
| 总耗时 | **约 118 秒**（CPU，最后一行 `time` 列） | 8 epoch |

模型规模：72 层、**3,005,843 参数**、8.1 GFLOPs；推理 **12.8 ms/图**（CPU）。

### 3.3 逐 epoch 训练曲线（`runs/tongue/demo-locator/results.csv`，真实数据）

| epoch | box_loss | cls_loss | P | R | mAP50 | mAP50-95 |
|---|---|---|---|---|---|---|
| 1 | 0.784 | 2.416 | 0.979 | 0.915 | 0.977 | 0.705 |
| 2 | 0.720 | 0.922 | 1.000 | 0.998 | 0.995 | 0.740 |
| 3 | 0.673 | 0.776 | 0.936 | 0.540 | **0.707** | 0.497 |
| 4 | 0.690 | 0.750 | 0.961 | 0.988 | 0.993 | 0.851 |
| 5 | 0.623 | 0.672 | 0.961 | 0.800 | 0.887 | 0.714 |
| 6 | 0.579 | 0.621 | 0.999 | 1.000 | 0.995 | 0.890 |
| 7 | 0.575 | 0.599 | 0.999 | 1.000 | 0.995 | 0.910 |
| 8 | 0.528 | 0.603 | 0.999 | 1.000 | 0.995 | **0.952** |

**读法**：第 2 个 epoch 就基本收敛（单类、目标大、场景单一），第 3 个 epoch 的塌陷是增强（mosaic）尚未关闭时的典型抖动；`mAP50-95` 持续爬升说明框在越贴越准。**这不是"模型强"，是任务简单**。

---

## 4. 定位验收与复现（2026-09-11 实测）

### 4.1 项目自带评估脚本（`scripts/evaluate_tongue.py` → `app/services/tongue_evaluation.py`）

`tongue_evaluation.py` 自己实现了 IoU / TP-FP-FN / P-R-F1（不依赖 pycocotools），并明确把分类指标标记为不可评估：

```python
"classification": classification_evaluation_status(0, image_count),
# → {"status": "not_evaluable",
#    "reason": "现有舌象数据集没有舌色/苔质真值标注，无法计算分类准确率。"}
"acceptance": {
    "tongue_detection_recall_target": 0.95, "tongue_detection_recall_passed": recall >= 0.95,
    "classification_target": 0.85,          "classification_passed": False,
}
```

同一逻辑暴露为管理端接口 `GET /api/admin/tongue/evaluation?split=test`。

### 4.2 复现结果（本机跑 `scripts/evaluate_tongue.py`）

| 指标 | 本次复现 | MODEL_CARD 记录 |
|---|---|---|
| test 图片数 | 50 | 50 |
| TP / FP / FN | 50 / 0 / 0 | — |
| Precision | 1.0000 | 0.9988 |
| Recall | 1.0000 | 1.0000 |
| F1 | 1.0000 | — |
| 平均 IoU（IoU≥0.5 命中框） | **0.9323** | — |
| mAP50 | **0.995** | 0.9950 |
| mAP50-95 | **0.875** | 0.8747 |
| 舌体定位召回目标 0.95 | ✅ passed | ✅ |

> 复现命令见第 8 节。**50/50 全中、平均 IoU 0.93** 说明定位能力在本数据集上确实可用。

---

## 5. 舌色 / 苔质分类：训练步骤（关键，也是最大的坑）

### 5.1 模型结构（`app/services/tongue_classifier.py`）

```python
encoder = Conv(3→24,3x3)+ReLU+MaxPool  →  Conv(24→48)+ReLU+MaxPool  →  Conv(48→96)+ReLU+AdaptiveAvgPool(1x1)
dropout = Dropout(0.15)
color_head = Linear(96 → 3)      # 舌色：淡白 / 淡红 / 红
coat_head  = Linear(96 → 3)      # 苔质：薄白 / 厚腻 / 黄腻
forward → (color_logits, coat_logits)   # 共享编码器 + 双头多任务
```

**参数量 53,238**（实测），是个极小的演示网络。

### 5.2 标签怎么来的（`scripts/train_tongue_classifier.py` 的 `weak_labels()`）

**这是全链路最需要讲清楚的一点**：公开数据集只有舌体轮廓，**没有医生标注的舌色/苔质标签**。脚本用 ROI 的颜色统计"造"标签：

```python
r, g, b = 32x32 缩放后的通道均值
# 舌色弱标签
color = 2 if r > g*1.25 and r > b*1.35 else (1 if r > g*1.08 and r > b*1.15 else 0)
#   2=红   1=淡红   0=淡白
# 苔质弱标签
brightness = (r+g+b)/3
coat = 2 if r > b*1.2 and g > b*1.1 else (1 if brightness < 128 else 0)
#   2=黄腻  1=厚腻  0=薄白
```

脚本 docstring 自己写明了这个局限：

> *"The current public locator corpus has no colour/coating annotations. This script therefore creates transparent weak labels from ROI colour statistics... Replace the labels with clinician annotations before clinical use."*

### 5.3 训练循环

```python
dataset = TongueDataset("data/tongue_dataset", "train")
#   每张图：先用 train/labels 的 bbox 裁剪出 ROI → Resize(128,128) → ToTensor
#   标签：weak_labels(ROI) 现算（不读任何人工标注文件）
loader = DataLoader(dataset, batch_size=32, shuffle=True)
model = TongueMultiHeadClassifier()
optimizer = AdamW(lr=2e-3, weight_decay=1e-4)
loss = CE(color_logits, colors) + CE(coat_logits, coats)     # 两个头等权相加
for _ in range(epochs):   # 默认 5
    ...backward()
torch.save({"state_dict": ..., "classes": {...}, "label_source": "weak colour statistics from public locator corpus"}, out)
```

命令（写入 `models/tongue/tongue_classifier.pt`，**0.21 MB**）：

```bash
./venv/Scripts/python.exe scripts/train_tongue_classifier.py            # --epochs 5 --data-root data/tongue_dataset
```

### 5.4 实测诊断：这个分类头其实「没学会」

我把训练集弱标签分布与 test 集预测分布都统计了一遍（脚本见第 8 节）：

**① 训练标签分布（200 张）**

| 维度 | 分布 |
|---|---|
| 舌色 | **红 200 / 200（100%）** ← 弱标签规则把全数据集都判成"红" |
| 苔质 | 薄白 62 / 厚腻 39 / 黄腻 99 |

**② 模型在 test（50 张）上的预测分布**

| 维度 | 分布 | 平均置信度 |
|---|---|---|
| 舌色 | **红 50 / 50** | 0.9885（虚高，因为训练标签只有一个类） |
| 苔质 | **黄腻 50 / 50** | **0.4472**（随机基线 1/3 = 0.3333） |

**③ 端到端 5 张测试图（走 `analyze_tongue`）**：全部输出「舌色=红（conf ≈0.99）、苔质=黄腻（conf ≈0.46）」，`classifier=tongue_multitask_v1`。

**结论（必须如实说明）**：

1. **舌色头退化成常量分类器** —— 训练标签全是「红」，学到的最优解就是"永远输出红"，置信度 0.99 毫无意义；
2. **苔质头 ≈ 猜多数类** —— 50 张全判「黄腻」（训练集多数类），且平均置信度 0.447 只比随机 0.333 高一点，说明特征里几乎没有可分的苔质信息；
3. 根因是**弱标签与输入特征同源**：标签本身就是"平均 RGB 的比值"，模型又在这张 ROI 上学同样的统计量，于是学成"数据集平均色 → 一个恒定类"；颜色头因为阈值把 200 张全判红，连类间区分都没有；
4. 所以 `acceptance.classification_passed` 恒为 `False`、`status=not_evaluable` **是设计上诚实的结果，不是漏做**。

> ⚠️ 答辩如果被问"舌苔识别准不准"：**不要说 85%、也不要说 99%**。正确回答是"定位已达标（R 1.0 / mAP50 0.995）；舌色苔质当前是弱标签演示构建，我们如实标记为不可评估，需要临床标注数据才能真正训练"。

---

## 6. 推理与产品化（可以讲的部分）

### 6.1 三条降级路径（`app/services/tongue_service.py`）

| 情况 | 行为 | 返回 `status` |
|---|---|---|
| 权重文件不存在 | 整图规则观察（颜色统计 + 亮度判断苔厚） | `demo`（`demo: true` + DEMO 徽标） |
| 权重在、但没检出舌体 | 提示重拍，**不落库** | `not_detected` |
| 权重在、检出 | 逐框 ROI → 分类头优先，异常回退规则观察 | `detected` |

设计要点：

- **惰性加载 + 进程内缓存**（`_model` / `_classifier` 全局变量），避免每请求重载权重；
- 代码里留了一条**踩坑注释**：加载逻辑必须留在 `_get_model()` 内，历史上因缩进错误落进 `_get_classifier()` 的 `return` 之后成了死代码，导致"权重存在却一直显示未加载"；
- `_observe_roi` **始终先算规则观察**，分类模型只是"覆盖"结果 → 任何异常都不影响主链路（`logger.warning` + 回退）；
- `max_det=3`、`conf` 走配置 `TONGUE_YOLO_CONF=0.35`，权重路径走 `TONGUE_YOLO_MODEL`，分类模型走 `TONGUE_CLASSIFIER_MODEL`（**可用环境变量替换，便于现场换模型/演示降级**）。

### 6.2 建议层（`app/services/tongue_advice.py`）

把「色 + 苔 + 置信度」翻译成用户能懂的话：

- `COLOR_INFO` / `COAT_INFO`：每类给 `label` / `plain`（通俗解读）/ `tips`（3~4 条可执行建议，如"每餐加一份蔬菜、饭后散步 10–15 分钟"）；
- 建议**先苔后色**合并去重，最多 6 条；
- `_quality_note(confidence)` 直接把置信度翻译成照片质量提示（≥0.85 清晰 / ≥0.6 一般 / 否则建议重拍）——**这是掩盖分类头置信度不可靠的合规做法：只用来判断"照片能不能用"，不宣称识别准确**；
- 固定 `WATCH`（出现口苦口臭腹胀等请就医）+ `DISCLAIMER`（观察参考，非诊断）。

### 6.3 落库与隐私（F9-08/09、C-06）

`app/models/tongue.py` → `tongue_records`：

| 列 | 类型 | 说明 |
|---|---|---|
| `box` / `detail` | `EncryptedJSON`（AES-GCM） | 检测框与分析快照，库里是 `enc:v1:` 密文 |
| `image_url` / `image_object_name` | `EncryptedText` | 图片访问地址与对象名加密 |
| `image_bucket` | 明文 | `health-tongue` 私有桶 |
| `tongue_color` / `coat` / `confidence` | 明文 | 便于统计与趋势（非敏感） |

- 原图**客户端加密**后写入 MinIO 私有桶（`upload_private_encrypted_bytes`）；
- 回显走**带 Token 的网关接口** `GET /api/tongue/images/{record_id}`（校验 `user_id` 归属，非本人 404），**不暴露 MinIO 直链**；
- 隐私模块接入：数据导出包含舌象记录、删除数据时同步清理（并登记对象删除任务）。

### 6.4 前端（`frontend/src/views/TonguePage.vue`）

- 选图 → 本地预览 → `POST /tongue/analyze`；
- **canvas 画框**：按图片原始尺寸绘制所有 `detections` 框 + 置信度标签（`4DE3FF` 描边、半透明底标签）；
- 结果卡显示 `status` 文案（已检测/演示模式/未检测）、色苔解读、建议、照片质量、免责声明；
- **趋势**：`getTongueRecords` 拉历史 → 倒序时间轴，圆点颜色按舌色映射，`trendSummary` 比较最近两次（"舌色由「红」变为「淡红」；苔质由…"）。

---

## 7. 已知坑（复现必踩）

### 7.1 `tongue.yaml` 的相对路径会被 ultralytics 全局设置劫持

`path: data/tongue_dataset` 是相对路径，Ultralytics 会拿**全局 `datasets_dir`** 去解析，而不是 yaml 所在目录。本机该设置为另一个项目：

```
C:\Users\26912\Desktop\智能AI测评\ai_talent\datasets
```

直接 `model.val(data="data/tongue.yaml")` 会报：

```
FileNotFoundError: Dataset 'D:/.../backend/data/tongue.yaml' images not found,
missing path 'C:\Users\26912\Desktop\智能AI测评\ai_talent\datasets\data\tongue_dataset\test\images'
```

**注意**：`settings.update({"datasets_dir": ...})` 在运行期**无效**——`DATASETS_DIR` 是 ultralytics 导入期常量，改设置不会回灌。

**两个可行解法**：

1. **绝对路径版 yaml**（推荐，不动全局设置）：
   ```yaml
   path: D:/项目阶段/项目实操/智能健康测评/backend/data/tongue_dataset
   ```
   但 yaml 里有中文路径时注意文件要按 UTF-8 存（用 PowerShell `-Encoding ascii` 会把中文写成 `????`）。
2. **把数据集映射到纯 ASCII 路径**（本次复现采用）：建 junction 再写 ASCII yaml：
   ```powershell
   New-Item -ItemType Junction -Path C:\...\tongue_ds_link `
            -Target "D:\项目阶段\项目实操\智能健康测评\backend\data\tongue_dataset"
   ```
   ```yaml
   path: C:/Users/26912/WorkBuddy/2026-09-11-09-38-08/tongue_ds_link
   ```

> 项目自带的 `scripts/evaluate_tongue.py` / 管理端 `/api/admin/tongue/evaluation` **不受影响**——它们传的是绝对路径 `Path(data_root)`。

### 7.2 其他

- 训练/推理都是 **CPU**（`torch 2.14.0+cpu`、Ryzen 5 4600H），GPU 环境下 `imgsz/epochs` 可以放大，但**本任务没必要**（单类大目标）；
- `ultralytics>=8.3` 在 `requirements.txt` 里；但 **torch/torchvision 没有写进 requirements.txt**（实测 2.14.0+cpu），换机部署要单独装；
- 数据来源可能含**增强图**（旋转/翻转，测试图为 `randomRotation*.png`），因此 mAP 数字**不代表泛化能力**，MODEL_CARD 已声明；
- 分类头置信度**不能当作"识别把握度"对外宣称**（第 5.4 节已证）。

---

## 8. 完整复现命令清单（本机实测可用）

```bash
cd "D:/项目阶段/项目实操/智能健康测评/backend"

# ① 定位验收（自带脚本，绝对路径，不受 7.1 影响）
./venv/Scripts/python.exe scripts/evaluate_tongue.py
#   → precision 1.0 / recall 1.0 / iou 0.9323 / classification: not_evaluable

# ② 官方 mAP 复现（需先用 junction 生成 ASCII yaml，见 7.1）
./venv/Scripts/python.exe -c "
from ultralytics import YOLO
m = YOLO('models/tongue/yolov8n-tongue.pt')
v = m.val(data=r'C:/Users/26912/WorkBuddy/2026-09-11-09-38-08/tongue_abs.yaml',
          split='test', imgsz=256, batch=16, device='cpu', plots=False)
print(round(float(v.box.mp),4), round(float(v.box.mr),4), round(float(v.box.map50),4), round(float(v.box.map),4))
"
#   → 0.999 1.0 0.995 0.875

# ③ 端到端推理（走服务层，含分类头）
./venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from pathlib import Path
from app.services.tongue_service import analyze_tongue
p = sorted(Path('data/tongue_dataset/test/images').glob('*'))[0]
r = analyze_tongue(p.read_bytes(), 'image/jpeg')
print(r['status'], r['best']['box'], r['best']['tongue_color_observation'], r['best']['coat_observation'])
"

# ④ 重新训练定位模型（8 epoch / 256px / CPU ≈ 2 分钟）
./venv/Scripts/python.exe scripts/train_tongue_yolo.py \
    --data data/tongue.yaml --epochs 8 --imgsz 256 --batch 16 --device cpu \
    --project runs/tongue --name demo-locator

# ⑤ 重新训练分类头（弱标签，5 epoch）
./venv/Scripts/python.exe scripts/train_tongue_classifier.py

# ⑥ 测试套件
./venv/Scripts/python.exe -m pytest tests/ -q       # 11 passed
```

**第 5.4 节诊断数据的复现脚本**（临时脚本，不属于项目代码，可删）：

```bash
# 弱标签分布 + test 集预测分布（复现「训练标签全红 / 输出恒定」的证据）
./venv/Scripts/python.exe "C:/Users/26912/WorkBuddy/2026-09-11-09-38-08/tmp_tongue_diag.py"
#   → tongue_diag.json

# 定位评估 + 端到端 5 张图推理（含分类头输出与置信度）
./venv/Scripts/python.exe "C:/Users/26912/WorkBuddy/2026-09-11-09-38-08/tmp_tongue_repro.py"
#   → tongue_eval_report.json
```

---

## 9. 如果要把它做成"真的能用"

按投入从低到高：

| 优先级 | 动作 | 解决什么问题 |
|---|---|---|
| P0 | **换掉弱标签**：找中医/口腔科医生对 500–1000 张舌象标注 `舌色(淡白/淡红/红/绛/紫)` 与 `苔质(薄白/白腻/黄腻/灰黑/剥苔)`，至少双人标注 + 一致性检验（Cohen's kappa） | 让分类头第一次有真值可学（当前 200 张全红） |
| P0 | **加评估脚本**：分层 Top-1 / 混淆矩阵 / 每类 F1，替换现在的 `not_evaluable` | 答辩可给出"某类准确率 + 混淆矩阵"，而不是空话 |
| P1 | **拍摄标准化**：色卡校正 / 固定光源 / 距离角度提示，入库前做白平衡校验 | 颜色统计类特征对白平衡极敏感，是当前预测不稳定的主因之一 |
| P1 | 数据多样性：手机拍摄（不同机型/光源/背景）而非同一来源增强图 | 当前 mAP 虚高，换真实照片会明显掉点 |
| P2 | 分类头换轻量骨干（如 MobileNetV3 / EfficientNet-B0）+ 数据增强 + 类别权重 | 53k 参数的小 CNN 容量有限 |
| P2 | 引入"不确定"输出：置信度低于阈值时返回"建议重拍"而不是硬给一类 | 避免把瞎猜包装成结论（当前苔质 conf 0.45 仍在给结论） |
| P3 | 舌体分割替代检测（上游本就是分割标注），用 ROI 形状特征辅助齿痕/裂纹 | 目前这些特征完全没做，MODEL_CARD 也明确"不做" |

---

## 10. 合规边界（答辩必须守住）

- 全程措辞为**观察参考**，不出现"诊断/证型/疗效"；`tongue_advice` 已内置 `WATCH` + `DISCLAIMER`；
- 测试用例 `docs/功能测试用例_F7_F9_合规.md` 第 5 节（F9-01~F9-11）中，**F9-02~F9-09 必须通过**才构成"定位+分类+保存+私有图片读取"闭环；同文件第 181 行明确要求：
  > *"F9 的分类模型仅用于健康观察演示，不得把测试通过写成医疗诊断准确率或临床有效性结论。"*
- `MODEL_CARD.md` 已声明：指标为小规模公开数据集上的**演示级定位测量**，不代表泛化能力，不可用于医疗声明。

---

**文档生成日期**：2026-09-11 ｜ **复现环境**：Windows / Python 3.13.14 / torch 2.14.0+cpu / ultralytics 8.4.145 / CPU: Ryzen 5 4600H
