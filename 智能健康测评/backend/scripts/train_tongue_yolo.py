"""Train tongue detector weights with Ultralytics YOLO.

默认沿用 Ultralytics 原生增强，但舌象检测有特殊性，可用参数覆盖。

背景：同一份标注里既有「整舌级」大框（白苔/红舌盖住整个舌面），也有「局部级」小框
（红点约 4×9 像素、裂纹细条）。因此 mosaic（四图拼接）与 erasing（随机遮挡）会破坏
整舌语义，scale 过大则让小目标彻底消失。

实测（2026-09-11，TCM-Tongue 14 类 / 100 epoch / imgsz 640 / batch 32）：
  用 Ultralytics 默认增强 → precision 0.380 / recall 0.388 / mAP50 0.388 / mAP50-95 0.299
  且逐类指标呈现「框越大越准」：白苔 0.95、黄苔 0.84 … 红点舌 0.014、滑苔 0.002

舌象推荐配置：
  --mosaic 0.0 --erasing 0.0 --scale 0.25 --translate 0.05 --fliplr 0.0 --cls 1.0
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default='data/tongue.yaml')
    parser.add_argument('--base', default='yolov8n.pt')
    parser.add_argument('--epochs', type=int, default=80)
    parser.add_argument('--imgsz', type=int, default=640)
    parser.add_argument('--project', default='runs/tongue')
    parser.add_argument('--name', default='tongue')
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--device', default=None, help='e.g. cpu, 0, or omit for auto')

    # ---- 增强（不传则沿用 Ultralytics 默认值）----
    parser.add_argument('--mosaic', type=float, default=None, help='四图拼接概率，舌象建议 0.0')
    parser.add_argument('--erasing', type=float, default=None, help='随机擦除概率，舌象建议 0.0')
    parser.add_argument('--mixup', type=float, default=None)
    parser.add_argument('--scale', type=float, default=None, help='随机缩放幅度，舌象建议 0.25')
    parser.add_argument('--translate', type=float, default=None, help='随机平移幅度，舌象建议 0.05')
    parser.add_argument('--fliplr', type=float, default=None, help='水平翻转，舌象建议 0.0')
    parser.add_argument('--flipud', type=float, default=None)
    parser.add_argument('--degrees', type=float, default=None)
    parser.add_argument('--hsv-h', dest='hsv_h', type=float, default=None)
    parser.add_argument('--hsv-s', dest='hsv_s', type=float, default=None,
                        help='饱和度扰动，舌色任务建议 <=0.3')
    parser.add_argument('--hsv-v', dest='hsv_v', type=float, default=None,
                        help='明度扰动，舌色任务建议 <=0.3')
    # ---- 损失与优化 ----
    parser.add_argument('--cls', dest='cls_gain', type=float, default=None,
                        help='分类损失权重，多类别多标签任务建议 1.0（Ultralytics 默认 0.5）')
    parser.add_argument('--lr0', type=float, default=None)
    parser.add_argument('--patience', type=int, default=None)
    parser.add_argument('--optimizer', default=None, help='SGD / AdamW / auto')
    parser.add_argument('--close-mosaic', type=int, default=None)
    parser.add_argument('--seed', type=int, default=None)
    args = parser.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.base)
    train_args = {
        'data': args.data, 'epochs': args.epochs, 'imgsz': args.imgsz,
        'project': args.project, 'name': args.name, 'batch': args.batch,
    }
    if args.device:
        train_args['device'] = args.device

    optional = {
        'mosaic': args.mosaic, 'erasing': args.erasing, 'mixup': args.mixup,
        'scale': args.scale, 'translate': args.translate, 'fliplr': args.fliplr,
        'flipud': args.flipud, 'degrees': args.degrees,
        'hsv_h': args.hsv_h, 'hsv_s': args.hsv_s, 'hsv_v': args.hsv_v,
        'cls': args.cls_gain, 'lr0': args.lr0, 'patience': args.patience,
        'optimizer': args.optimizer, 'close_mosaic': args.close_mosaic,
        'seed': args.seed,
    }
    for key, value in optional.items():
        if value is not None:
            train_args[key] = value

    print('训练参数：', {k: v for k, v in train_args.items() if k != 'data'})
    model.train(**train_args)
    print('best weights:', Path(args.project) / args.name / 'weights' / 'best.pt')


if __name__ == '__main__':
    main()
