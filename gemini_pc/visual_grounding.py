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
        quality: int = 80
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
        last_action_coord: Optional[Tuple[int, int]] = None,
        current_mouse_coord: Optional[Tuple[int, int]] = None,
    ) -> Image.Image:
        """
        Draws an ultra-high-precision 0-1000 normalized coordinate system overlay.
        Rulers along ALL 4 BORDERS (Top, Bottom, Left, Right) with 25-unit tick marks provide
        pinpoint references everywhere on screen, especially for taskbar icons and bottom buttons.
        Renders the current mouse cursor location and last action marker for closed-loop visual grounding.
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

        # 6. Prominent Synthetic Mouse Cursor Crosshair & Coordinate Badge
        if current_mouse_coord:
            mx, my = current_mouse_coord
            if 0 <= mx < w and 0 <= my < h:
                mnx = int(round(mx / float(w) * 1000.0))
                mny = int(round(my / float(h) * 1000.0))

                # Outer crosshair circle in vibrant cyan
                cr = 14
                draw.ellipse([(mx - cr, my - cr), (mx + cr, my + cr)], outline=(6, 182, 212, 240), width=2)
                # Inner targeting circle
                cr_in = 5
                draw.ellipse([(mx - cr_in, my - cr_in), (mx + cr_in, my + cr_in)], outline=(255, 255, 255, 255), width=2)
                # Center point
                draw.ellipse([(mx - 2, my - 2), (mx + 2, my + 2)], fill=(6, 182, 212, 255))
                # 4-way crosshair lines extending outward
                draw.line([(mx - 22, my), (mx - 6, my)], fill=(6, 182, 212, 240), width=2)
                draw.line([(mx + 6, my), (mx + 22, my)], fill=(6, 182, 212, 240), width=2)
                draw.line([(mx, my - 22), (mx, my - 6)], fill=(6, 182, 212, 240), width=2)
                draw.line([(mx, my + 6), (mx, my + 22)], fill=(6, 182, 212, 240), width=2)

                # Cursor badge: CURSOR: [x=..., y=...]
                cur_tag = f"CURSOR: [{mnx}, {mny}]"
                cbox = font_bold.getbbox(cur_tag)
                ctw, cth = cbox[2] - cbox[0], cbox[3] - cbox[1]
                cur_x = min(max(mx + 14, 4), w - ctw - 8)
                cur_y = my + 14 if my <= h - 45 else my - 30
                draw.rectangle(
                    [(cur_x - 3, cur_y - 2), (cur_x + ctw + 5, cur_y + cth + 4)],
                    fill=(8, 47, 73, 235),
                    outline=(6, 182, 212, 220)
                )
                draw.text((cur_x + 1, cur_y + 1), cur_tag, fill=(103, 232, 249, 255), font=font_bold)

        return canvas

    @classmethod
    def create_zoom_crop(
        cls,
        img: Image.Image,
        center_x: int,
        center_y: int,
        box_size: int = 300,
    ) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
        """
        Extracts a box_size x box_size (default 300x300) crop centered at (center_x, center_y) in physical pixels.
        Overlays a fine 0-100 micro-grid with tick marks every 5 units, major lines every 10 units,
        and border rulers for Stage 2 sub-pixel accuracy targeting.
        Returns (cropped_with_grid, (crop_x1, crop_y1, crop_x2, crop_y2)).
        """
        w, h = img.size
        half = box_size // 2

        # Boundary clamped crop rectangle
        x1 = max(0, min(center_x - half, w - box_size))
        y1 = max(0, min(center_y - half, h - box_size))
        x2 = min(w, x1 + box_size)
        y2 = min(h, y1 + box_size)

        crop = img.crop((x1, y1, x2, y2)).copy()
        draw = ImageDraw.Draw(crop, "RGBA")
        cw, ch = crop.size

        font_micro = cls._get_font(size=9, bold=True)
        font_header = cls._get_font(size=10, bold=True)

        # Micro-grid lines (0 to 100 scale, where 1 unit = 3.0px on a 300x300 crop)
        for u in range(10, 100, 10):
            px = int(round(u / 100.0 * cw))
            py = int(round(u / 100.0 * ch))

            if u == 50:
                col = (251, 191, 36, 190)  # Amber center axis
                width = 2
            else:
                col = (56, 189, 248, 75)
                width = 1

            draw.line([(px, 0), (px, ch)], fill=col, width=width)
            draw.line([(0, py), (cw, py)], fill=col, width=width)

        # Minor tick marks every 5 units along borders
        for u in range(5, 100, 5):
            px = int(round(u / 100.0 * cw))
            py = int(round(u / 100.0 * ch))
            tlen = 6 if u % 10 == 0 else 3

            draw.line([(px, 0), (px, tlen)], fill=(56, 189, 248, 220), width=1)
            draw.line([(px, ch - tlen), (px, ch)], fill=(56, 189, 248, 220), width=1)
            draw.line([(0, py), (tlen, py)], fill=(56, 189, 248, 220), width=1)
            draw.line([(cw - tlen, py), (cw, py)], fill=(56, 189, 248, 220), width=1)

        # Labeled coordinate badges every 20 units
        for u in range(20, 100, 20):
            px = int(round(u / 100.0 * cw))
            py = int(round(u / 100.0 * ch))
            lbl = f"{u}"
            bbox = font_micro.getbbox(lbl)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            # Top label badge
            bx = px - tw // 2
            draw.rectangle([(bx - 2, 0), (bx + tw + 2, th + 2)], fill=(15, 23, 42, 230), outline=(56, 189, 248, 140))
            draw.text((bx, 0), lbl, fill=(253, 224, 71, 255), font=font_micro)

            # Left label badge
            by = py - th // 2
            draw.rectangle([(0, by - 1), (tw + 4, by + th + 2)], fill=(15, 23, 42, 230), outline=(56, 189, 248, 140))
            draw.text((2, by), lbl, fill=(253, 224, 71, 255), font=font_micro)

        # Center bullseye reticle at [50, 50]
        cx = int(round(0.5 * cw))
        cy = int(round(0.5 * ch))
        draw.ellipse([(cx - 8, cy - 8), (cx + 8, cy + 8)], outline=(251, 191, 36, 220), width=2)
        draw.ellipse([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=(251, 191, 36, 255))

        # Header tag
        hdr = "STAGE 2 MICRO-GRID (0-100)"
        hbbox = font_header.getbbox(hdr)
        htw, hth = hbbox[2] - hbbox[0], hbbox[3] - hbbox[1]
        draw.rectangle([(cw - htw - 8, ch - hth - 6), (cw, ch)], fill=(15, 23, 42, 230), outline=(56, 189, 248, 120))
        draw.text((cw - htw - 4, ch - hth - 5), hdr, fill=(56, 189, 248, 255), font=font_header)

        return crop, (x1, y1, x2, y2)

    @staticmethod
    def microgrid_to_screen_coords(u: float, v: float, crop_bounds: Tuple[int, int, int, int]) -> Tuple[int, int]:
        """Maps micro-grid (0-100) coordinates back to physical screen pixels."""
        x1, y1, x2, y2 = crop_bounds
        u_clamped = max(0.0, min(float(u), 100.0))
        v_clamped = max(0.0, min(float(v), 100.0))
        px = int(round(x1 + (u_clamped / 100.0) * (x2 - x1)))
        py = int(round(y1 + (v_clamped / 100.0) * (y2 - y1)))
        return px, py

    @staticmethod
    def to_base64_data_url(jpeg_bytes: bytes) -> str:
        b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
