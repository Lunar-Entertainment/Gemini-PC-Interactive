import io
import base64
from typing import Tuple, Optional, NamedTuple
from PIL import Image, ImageDraw, ImageFont


class OptimizedImage(NamedTuple):
    bytes: bytes
    orig_size: Tuple[int, int]
    sent_size: Tuple[int, int]


class VisualGrounding:
    """Provides high-precision coordinate grid overlay, visual landmarks, and image optimization for Gemini vision."""

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
        # optimize=False saves 30-50ms CPU time per screenshot without noticeable quality loss
        resized.save(buffer, format="JPEG", quality=quality, optimize=False)
        return OptimizedImage(buffer.getvalue(), (orig_w, orig_h), (new_w, new_h))

    @staticmethod
    def draw_coordinate_grid(
        img: Image.Image,
        grid_step: int = 100,
        last_action_coord: Optional[Tuple[int, int]] = None
    ) -> Image.Image:
        """
        Draws a high-precision coordinate grid with pixel numbers and labeled badges.
        Every 200px has a labeled coordinate badge [x, y], allowing Gemini to pinpoint
        small buttons with extreme accuracy anywhere on the screen.
        """
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas, "RGBA")
        w, h = canvas.size

        font = ImageFont.load_default()

        # 1. Subtle high-contrast grid lines
        grid_color = (0, 210, 255, 55)  # Cyan
        for x in range(0, w, grid_step):
            draw.line([(x, 0), (x, h)], fill=grid_color, width=1)
        for y in range(0, h, grid_step):
            draw.line([(0, y), (w, y)], fill=grid_color, width=1)

        # 2. Top and left border axis tick labels
        for x in range(0, w, grid_step):
            lbl = f"{x}"
            bbox = font.getbbox(lbl)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.rectangle([(x, 0), (x + tw + 4, th + 3)], fill=(15, 23, 42, 210))
            draw.text((x + 2, 1), lbl, fill=(56, 189, 248, 255), font=font)

        for y in range(grid_step, h, grid_step):
            lbl = f"{y}"
            bbox = font.getbbox(lbl)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.rectangle([(0, y), (tw + 4, y + th + 3)], fill=(15, 23, 42, 210))
            draw.text((2, y + 1), lbl, fill=(56, 189, 248, 255), font=font)

        # 3. High-contrast coordinate badges at 200px intersections across viewport
        badge_bg = (15, 23, 42, 195)
        badge_border = (56, 189, 248, 140)
        badge_text_color = (253, 224, 71, 245)  # Bright amber/yellow

        for x in range(200, w - 50, 200):
            for y in range(200, h - 50, 200):
                text = f"[{x},{y}]"
                bbox = font.getbbox(text)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.rectangle([(x - 2, y - 2), (x + tw + 4, y + th + 3)], fill=badge_bg, outline=badge_border)
                draw.text((x + 1, y), text, fill=badge_text_color, font=font)

        # 4. Prominent Last Action Bullseye Marker (Visual Feedback)
        if last_action_coord:
            lx, ly = last_action_coord
            if 0 <= lx < w and 0 <= ly < h:
                # Outer ring
                r = 16
                draw.ellipse([(lx - r, ly - r), (lx + r, ly + r)], outline=(244, 63, 94, 240), width=3)
                # Inner ring
                r_in = 6
                draw.ellipse([(lx - r_in, ly - r_in), (lx + r_in, ly + r_in)], outline=(255, 255, 255, 255), width=2)
                # Center point
                draw.ellipse([(lx - 2, ly - 2), (lx + 2, ly + 2)], fill=(244, 63, 94, 255))
                # 4-way crosshairs
                draw.line([(lx - 24, ly), (lx + 24, ly)], fill=(244, 63, 94, 230), width=2)
                draw.line([(lx, ly - 24), (lx, ly + 24)], fill=(244, 63, 94, 230), width=2)

                # Last click coordinate tag
                tag = f"LAST: ({lx},{ly})"
                tbox = font.getbbox(tag)
                ttw, tth = tbox[2] - tbox[0], tbox[3] - tbox[1]
                tag_x = min(max(lx - ttw // 2, 4), w - ttw - 8)
                tag_y = ly - 32 if ly >= 36 else ly + 18
                draw.rectangle([(tag_x - 2, tag_y - 2), (tag_x + ttw + 4, tag_y + tth + 3)],
                               fill=(159, 18, 57, 230), outline=(255, 255, 255, 200))
                draw.text((tag_x + 1, tag_y), tag, fill=(255, 255, 255, 255), font=font)

        return canvas

    @staticmethod
    def to_base64_data_url(jpeg_bytes: bytes) -> str:
        b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
