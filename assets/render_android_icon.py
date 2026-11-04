"""Android launcher / notification icons from the desktop icon (assets/learning_plus.png).

Run after render_icon.py whenever the desktop icon changes:
    python assets/render_android_icon.py

- Adaptive icon (Android 8+): the whole desktop icon fills the 72 dp visible square of the
  108 dp foreground layer; the background layer is the same picture enlarged and blurred, so
  launchers whose mask reaches past 72 dp show matching colour instead of an edge.
- Legacy icons (Android 7): rounded square and round versions.
- Notification icon: white silhouette of the star mark (Android only uses the alpha channel).
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "android" / "app" / "src" / "main" / "res"
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def draw_badge(icon: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """The PLUS badge exactly as render_icon.py draws it (1024 px icon coordinates)."""
    shadow = Image.new("RGBA", icon.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 12, box[2], box[3] + 12), radius=64, fill=(80, 18, 22, 90))
    icon = Image.alpha_composite(icon, shadow.filter(ImageFilter.GaussianBlur(18)))
    draw = ImageDraw.Draw(icon)
    draw.rounded_rectangle(box, radius=64, fill="#fffdf8", outline="#ffd88a", width=6)
    font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arialbd.ttf"), 76)
    tb = draw.textbbox((0, 0), "PLUS", font=font)
    tx = box[0] + (box[2] - box[0] - (tb[2] - tb[0])) / 2 - tb[0]
    ty = box[1] + (box[3] - box[1] - (tb[3] - tb[1])) / 2 - tb[1]
    draw.text((tx, ty), "PLUS", fill="#d8232f", font=font)
    return icon


# Adaptive icons may be masked to a circle, which cuts the desktop badge's corner position
# (56, 56). Here it sits further in so all of its corners stay inside the circle.
ROUND_BADGE = (160, 168, 470, 296)


def rounded(img: Image.Image, radius_ratio: float) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    r = int(img.width * radius_ratio)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.width - 1, img.height - 1), r, fill=255)
    out = img.copy()
    out.putalpha(mask)
    return out


def circle(img: Image.Image) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, img.width - 1, img.height - 1), fill=255)
    out = img.copy()
    out.putalpha(mask)
    return out


def main() -> None:
    src = Image.open(HERE / "learning_plus.png").convert("RGBA")
    official = Image.open(HERE / "chaoxing_official.jpg").convert("RGBA").resize((1024, 1024), Image.LANCZOS)
    # Background layer art: the official logo; the badge is the foreground layer on top.
    badge_only = draw_badge(Image.new("RGBA", (1024, 1024), (0, 0, 0, 0)), ROUND_BADGE)
    round_icon = Image.alpha_composite(official, badge_only)  # what a round launcher shows

    for name, scale in DENSITIES.items():
        layer = round(108 * scale)
        visible = round(72 * scale)
        legacy = round(48 * scale)
        pad = (layer - visible) // 2
        folder = RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)

        bg = official.resize((layer, layer), Image.LANCZOS).filter(ImageFilter.GaussianBlur(layer / 10))
        art = official.resize((visible, visible), Image.LANCZOS)
        bg.paste(art, (pad, pad), art)
        bg.save(folder / "ic_launcher_background.png")

        fg = Image.new("RGBA", (layer, layer), (0, 0, 0, 0))
        badge = badge_only.resize((visible, visible), Image.LANCZOS)
        fg.paste(badge, (pad, pad), badge)
        fg.save(folder / "ic_launcher_foreground.png")

        # Square like the desktop icon (no rounded corners); launchers apply their own mask.
        src.resize((legacy, legacy), Image.LANCZOS).save(folder / "ic_launcher.png")
        circle(round_icon.resize((legacy, legacy), Image.LANCZOS)).save(folder / "ic_launcher_round.png")

    # In-app brand image (splash and the top-left brand row): square, exactly like the desktop icon.
    nodpi = RES / "drawable-nodpi"
    nodpi.mkdir(parents=True, exist_ok=True)
    src.resize((384, 384), Image.LANCZOS).save(nodpi / "brand_icon.png")

    # Notification: the white star and streaks, without the PLUS badge.
    gray = src.convert("RGB")
    w, h = gray.size
    mono = Image.new("L", (w, h), 0)
    px, out = gray.load(), mono.load()
    for y in range(h):
        for x in range(w):
            if x < 400 and y < 210:      # PLUS badge
                continue
            r, g, b = px[x, y]
            out[x, y] = max(0, min(255, (min(r, g, b) - 150) * 3))
    bbox = mono.getbbox()
    mark = mono.crop(bbox)
    side = max(mark.size)
    square = Image.new("L", (side, side), 0)
    square.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    for name, scale in DENSITIES.items():
        size = round(24 * scale)
        alpha = square.resize((size, size), Image.LANCZOS)
        icon = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        icon.putalpha(alpha)
        folder = RES / f"drawable-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        icon.save(folder / "ic_notify.png")
    print("icons written to", RES)


if __name__ == "__main__":
    main()
