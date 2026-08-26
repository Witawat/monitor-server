"""สร้างไอคอน 'monitor' (หน้าจอ + เส้น pulse) เป็น .ico หลายขนาด.

ใช้ Pillow วาดรูปที่ 256px แล้วย่อลงทุกขนาด → build/monitor.ico + monitor-256.png
รัน: python scripts/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

_ROOT = Path(__file__).resolve().parent.parent
_BUILD = _ROOT / "build"
_SIZES = [16, 24, 32, 48, 64, 128, 256]

# palette
_BG = (15, 23, 42)          # slate-900 พื้นหลัง tile
_BORDER = (30, 41, 59)      # slate-800 ขอบ tile
_FRAME = (13, 148, 136)     # teal-600 กรอบจอ
_SCREEN = (15, 118, 110)    # teal-700 พื้นจอ (เข้ม)
_PULSE = (34, 197, 94)      # green-500 เส้น pulse
_STAND = (148, 163, 184)    # slate-400 ขาตั้ง


def _rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], radius: float, fill, outline=None, width: int = 1) -> None:
    """วาดสี่เหลี่ยมมุมโค้ง."""

    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _draw(size: int) -> Image.Image:
    """วาดไอคอน monitor+pulse ขนาด size x size."""

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256.0  # scale factor

    def L(v: float) -> float:
        return v * s

    # tile (rounded square)
    pad = L(10)
    _rounded_rect(d, (pad, pad, size - pad, size - pad), L(56), _BG, outline=_BORDER, width=max(1, int(L(2))))

    # monitor frame (screen)
    frame_l, frame_t = L(40), L(48)
    frame_r, frame_b = L(216), L(196)
    _rounded_rect(d, (frame_l, frame_t, frame_r, frame_b), L(22), _SCREEN, outline=_FRAME, width=max(2, int(L(8))))

    # inner screen (darker area where pulse draws)
    inner = L(8)
    _rounded_rect(d, (frame_l + inner, frame_t + inner, frame_r - inner, frame_b - inner), L(14), _BG)

    # stand (neck + foot)
    neck_l, neck_t, neck_r, neck_b = L(120), frame_b, L(136), L(208)
    d.rectangle([neck_l, neck_t, neck_r, neck_b], fill=_STAND)
    foot_l, foot_t, foot_r, foot_b = L(96), L(204), L(160), L(218)
    d.rounded_rectangle([foot_l, foot_t, foot_r, foot_b], radius=L(8), fill=_STAND)

    # pulse (ECG) polyline across inner screen
    pts = [
        (L(56), L(128)),
        (L(76), L(128)),
        (L(84), L(104)),
        (L(96), L(150)),
        (L(104), L(150)),
        (L(114), L(96)),   # peak
        (L(126), L(150)),
        (L(136), L(150)),
        (L(146), L(112)),
        (L(156), L(138)),
        (L(170), L(122)),
        (L(184), L(128)),
        (L(200), L(128)),
    ]
    d.line(pts, fill=_PULSE, width=max(2, int(L(9))), joint="curve")
    return img


def main() -> None:
    """สร้าง .ico หลายขนาด + png พรีวิว."""

    _BUILD.mkdir(parents=True, exist_ok=True)
    icon = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    sizes = {s: _draw(s) for s in _SIZES}
    icon = sizes[256]
    icon.save(_BUILD / "monitor.ico", sizes=[(s, s) for s in _SIZES])
    icon.resize((256, 256)).save(_BUILD / "monitor-256.png")
    print("สร้าง icon แล้ว:", _BUILD / "monitor.ico", "sizes =", _SIZES)


if __name__ == "__main__":
    main()
