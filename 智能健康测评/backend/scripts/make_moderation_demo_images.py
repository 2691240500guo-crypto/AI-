"""生成社区机审演示图片。

用途：答辩演示「图片机审」——一张正常餐照（应通过）+ 一张违规广告图（应被拦截）。
运行：python scripts/make_moderation_demo_images.py
输出：backend/demo_images/
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "demo_images"
OUT.mkdir(exist_ok=True)


def _font(size: int):
    for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def make_normal_meal():
    """正常餐照示意图：应通过机审。"""
    img = Image.new("RGB", (640, 480), (245, 240, 230))
    d = ImageDraw.Draw(img)
    d.ellipse([120, 110, 520, 430], fill=(255, 255, 255), outline=(210, 200, 185), width=6)
    d.ellipse([190, 180, 330, 320], fill=(240, 190, 120))   # 主食
    d.ellipse([335, 195, 455, 300], fill=(140, 200, 130))   # 蔬菜
    d.ellipse([225, 305, 335, 385], fill=(215, 150, 140))   # 蛋白质
    d.text((40, 30), "今日健康午餐：藜麦 + 鸡胸 + 西兰花", fill=(60, 60, 60), font=_font(22))
    path = OUT / "demo_meal_normal.jpg"
    img.save(path, quality=88)
    return path


def make_violation_ad():
    """违规广告图：含引流联系方式 + 二维码 + 夸大功效文案，应被机审拦截。"""
    img = Image.new("RGB", (640, 480), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((30, 24), "特效减肥药 · 包治肥胖 · 三天见效", fill=(200, 0, 0), font=_font(26))
    d.text((30, 66), "祖传秘方 · 出售代购 · 加微信 abc123", fill=(200, 0, 0), font=_font(26))
    d.text((30, 108), "100% CURE · SALE WEIGHT LOSS PILLS · WeChat: abc123", fill=(150, 0, 0), font=_font(20))
    # 二维码样式方块
    random.seed(7)
    cell, x0, y0, size = 9, 300, 170, 20
    for r in range(size):
        for c in range(size):
            if random.random() < 0.45:
                d.rectangle([x0 + c * cell, y0 + r * cell, x0 + (c + 1) * cell, y0 + (r + 1) * cell], fill=(0, 0, 0))
    d.rectangle([x0 - 10, y0 - 10, x0 + size * cell + 10, y0 + size * cell + 10], outline=(0, 0, 0), width=4)
    path = OUT / "demo_ad_violation.jpg"
    img.save(path, quality=88)
    return path


if __name__ == "__main__":
    p1 = make_normal_meal()
    p2 = make_violation_ad()
    print("已生成演示图片：")
    print("  正常餐照（应通过）:", p1)
    print("  违规广告（应拦截）:", p2)
