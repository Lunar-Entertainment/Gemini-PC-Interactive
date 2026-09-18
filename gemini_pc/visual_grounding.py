import io
import os
import base64
from typing import Tuple, Optional, NamedTuple
from PIL import Image, ImageDraw, ImageFont


class OptimizedImage(NamedTuple):
    bytes: bytes
    orig_size: Tuple[int, int]
    sent_size: Tuple[int, int]


class VisualGrounding:
    """Provides high-precision 0-1000 normalized coordinate grid overlay, visual landmarks, and image optimization for Gemini vision."""

    _font_cache = {}

    @classmethod
    def _get_font(cls, size: int = 12, bold: bool = False) -> ImageFont.ImageFont:
        key = (size, bold)
        if key in cls._font_cache:
            return cls._font_cache[key]

        font_paths = [
            "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf",
        ]
        for path in font_paths:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    cls._font_cache[key] = font
                    return font
                except Exception:
                    pass

        default_font = ImageFont.load_default()
        cls._font_cache[key] = default_font
        return default_font

    @staticmethod
    def optimize_image(
        img: Image.Image,
        max_width: int = 1920,
        quality: int = 90
    ) -> OptimizedImage:
        """
        Resizes screenshot if needed and encodes to JPEG bytes.
        Returns OptimizedImage(bytes, (orig_w, orig_h), (sent_w, sent_h)).
        """
        orig_w, orig_h = img.size

        if orig_w > max_width:
            scale = max_width / float(orig_w)
            new_w = max_width
            new_h = int(round(orig_h * scale))
            resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        else:
            new_w, new_h = orig_w, orig_h
            resized = img

        buffer = io.BytesIO()
        # Convert RGBA or Palette to RGB if needed
        if resized.mode in ("RGBA", "P"):
            resized = resized.convert("RGB")
        resized.save(buffer, format="JPEG", quality=quality, optimize=False)
        return OptimizedImage(buffer.getvalue(), (orig_w, orig_h), (new_w, new_h))

    @classmethod
    def draw_coordinate_grid(
        cls,
        img: Image.Image,
        grid_step: int = 100,
        last_action_coord: Optional[Tuple[int, int]] = None
    ) -> Image.Image:
        """
        Draws an ultra-high-precision 0-1000 normalized coordinate system overlay.
        Rulers along ALL 4 BORDERS (Top, Bottom, Left, Right) with 25-unit tick marks provide
        pinpoint references everywhere on screen, especially for taskbar icons and bottom buttons.
        """
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas, "RGBA")
        w, h = canvas.size

        font = cls._get_font(size=11, bold=True)
        font_small = cls._get_font(size=9, bold=False)
        font_bold = cls._get_font(size=12, bold=True)

        # 1. Subtle, clear grid lines (every 50 and 100 units on 0-1000 scale)
        for u in range(50, 1000, 50):
            px = int(round(u / 1000.0 * w))
            py = int(round(u / 1000.0 * h))

            if u == 500:
                # Center axes in high-visibility golden amber
                line_color = (251, 191, 36, 140)
                width = 2
            elif u % 100 == 0:
                # Major 100-unit lines
                line_color = (56, 189, 248, 65)
                width = 1
            else:
                # Minor 50-unit lines
                line_color = (56, 189, 248, 30)
                width = 1

            draw.line([(px, 0), (px, h)], fill=line_color, width=width)
            draw.line([(0, py), (w, py)], fill=line_color, width=width)

        # 2. Precision tick markers every 25 units on ALL 4 BORDERS
        for u in range(25, 1000, 25):
            px = int(round(u / 1000.0 * w))
            py = int(round(u / 1000.0 * h))
            tlen = 8 if u % 50 == 0 else 4

            # Top and Bottom border ticks
            draw.line([(px, 0), (px, tlen)], fill=(56, 189, 248, 210), width=1)
            draw.line([(px, h - tlen), (px, h)], fill=(56, 189, 248, 210), width=1)

            # Left and Right border ticks
            draw.line([(0, py), (tlen, py)], fill=(56, 189, 248, 210), width=1)
            draw.line([(w - tlen, py), (w, py)], fill=(56, 189, 248, 210), width=1)

        # 3. Border Ruler Badges (every 100 units on Top, Bottom, Left, Right)
        for u in range(100, 1000, 100):
            px = int(round(u / 1000.0 * w))
            py = int(round(u / 1000.0 * h))
            lbl = f"{u}"
            bbox = font.getbbox(lbl)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            # Top badge
            badge_x = px - tw // 2
            draw.rectangle(
                [(badge_x - 3, 0), (badge_x + tw + 3, th + 4)],
                fill=(15, 23, 42, 235),
                outline=(56, 189, 248, 140)
            )
            draw.text((badge_x, 1), lbl, fill=(253, 224, 71, 255), font=font)

            # Bottom badge (directly above/at taskbar)
            draw.rectangle(
                [(badge_x - 3, h - th - 5), (badge_x + tw + 3, h)],
                fill=(15, 23, 42, 235),
                outline=(56, 189, 248, 140)
            )
            draw.text((badge_x, h - th - 4), lbl, fill=(253, 224, 71, 255), font=font)

            # Left badge
            badge_y = py - th // 2
            draw.rectangle(
                [(0, badge_y - 2), (tw + 7, badge_y + th + 3)],
                fill=(15, 23, 42, 235),
                outline=(56, 189, 248, 140)
            )
            draw.text((3, badge_y - 1), lbl, fill=(253, 224, 71, 255), font=font)

            # Right badge
            draw.rectangle(
                [(w - tw - 7, badge_y - 2), (w, badge_y + th + 3)],
                fill=(15, 23, 42, 235),
                outline=(56, 189, 248, 140)
            )
            draw.text((w - tw - 4, badge_y - 1), lbl, fill=(253, 224, 71, 255), font=font)

        # 4. Subtle Landmark Coordinate Pills across screen quadrants
        landmarks = [(250, 250), (750, 250), (500, 500), (250, 750), (750, 750), (500, 940)]
        for lx, ly in landmarks:
            cx = int(round(lx / 1000.0 * w))
            cy = int(round(ly / 1000.0 * h))
            tag = f"{lx},{ly}"
            tbox = font_small.getbbox(tag)
            ttw, tth = tbox[2] - tbox[0], tbox[3] - tbox[1]
            draw.rectangle(
                [(cx - ttw // 2 - 3, cy - tth // 2 - 2), (cx + ttw // 2 + 3, cy + tth // 2 + 2)],
                fill=(15, 23, 42, 190),
                outline=(56, 189, 248, 90)
            )
            draw.text((cx - ttw // 2, cy - tth // 2 - 1), tag, fill=(203, 213, 225, 220), font=font_small)

        # 5. Prominent Last Action Bullseye Marker (Visual Feedback)
        if last_action_coord:
            lx, ly = last_action_coord
            if 0 <= lx < w and 0 <= ly < h:
                nx = int(round(lx / float(w) * 1000.0))
                ny = int(round(ly / float(h) * 1000.0))

                # Outer ring
                r = 18
                draw.ellipse([(lx - r, ly - r), (lx + r, ly + r)], outline=(244, 63, 94, 240), width=3)
                # Inner ring
                r_in = 7
                draw.ellipse([(lx - r_in, ly - r_in), (lx + r_in, ly + r_in)], outline=(255, 255, 255, 255), width=2)
                # Center point
                draw.ellipse([(lx - 2, ly - 2), (lx + 2, ly + 2)], fill=(244, 63, 94, 255))
                # 4-way crosshairs
                draw.line([(lx - 26, ly), (lx + 26, ly)], fill=(244, 63, 94, 230), width=2)
                draw.line([(lx, ly - 26), (lx, ly + 26)], fill=(244, 63, 94, 230), width=2)

                # Last click normalized coordinate tag
                tag = f"LAST CLICK: [x={nx}, y={ny}]"
                tbox = font_bold.getbbox(tag)
                ttw, tth = tbox[2] - tbox[0], tbox[3] - tbox[1]
                tag_x = min(max(lx - ttw // 2, 4), w - ttw - 8)
                tag_y = ly - 36 if ly >= 42 else ly + 22
                draw.rectangle(
                    [(tag_x - 3, tag_y - 2), (tag_x + ttw + 5, tag_y + tth + 4)],
                    fill=(159, 18, 57, 240),
                    outline=(255, 255, 255, 220)
                )
                draw.text((tag_x + 1, tag_y + 1), tag, fill=(255, 255, 255, 255), font=font_bold)

        return canvas

    @staticmethod
    def to_base64_data_url(jpeg_bytes: bytes) -> str:
        b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
