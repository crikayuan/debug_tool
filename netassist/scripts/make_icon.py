from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sizes = [16, 24, 32, 48, 64, 128, 256]
out = Path(__file__).parent / "icon.ico"

images = []
for size in sizes:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = size // 8
    # 主色 #2f6fed 圆角背景
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill="#2f6fed")
    # 找合适字体（优先微软雅黑）
    font = None
    for fn in ["msyh.ttc", "msyh.ttf", "simhei.ttf", "arial.ttf"]:
        try:
            font = ImageFont.truetype(fn, int(size * 0.55))
            break
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()
    text = "调"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = (size - th) / 2 - bbox[1] - size * 0.04
    draw.text((x, y), text, font=font, fill="white")
    images.append(img)

images[0].save(out, format="ICO", sizes=[(im.width, im.height) for im in images])
print(f"saved {out} ({len(images)} sizes)")
