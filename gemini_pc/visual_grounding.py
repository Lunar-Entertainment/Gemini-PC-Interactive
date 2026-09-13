import io
import base64
from typing import Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

class VisualGrounding:
    """Provides coordinate grid overlay, visual markers, and image optimization for Gemini vision."""

    @staticmethod
    def optimize_image(img: Image.Image, max_width: int = 1600, quality: int = 80) -> Tuple[bytes, Tuple[int, int]]:
        """Resizes screenshot if needed and encodes to JPEG bytes."""
        orig_w, orig_h = img.size

        if orig_w > max_width:
            scale = max_width / float(orig_w)
            new_w = max_width
            new_h = int(orig_h * scale)
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            resized = img

        buffer = io.BytesIO()
        # Convert RGBA to RGB if needed
        if resized.mode in ("RGBA", "P"):
            resized = resized.convert("RGB")
        resized.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue(), (orig_w, orig_h)

    @staticmethod
    def draw_coordinate_grid(
        img: Image.Image,
        grid_step: int = 100,
        subdivisions: int = 4,
        last_action_coord: Optional[Tuple[int, int]] = None
    ) -> Image.Image:
        """
        Draws a subtle coordinate grid with pixel numbers on top of the image.
        This dramatically assists multimodal models in pinpointing small buttons accurately.
        """
        canvas = img.copy()
        draw = ImageDraw.Draw(canvas, "RGBA")
        w, h = canvas.size

        # Use default font
        font = ImageFont.load_default()

        # Vertical lines
        for x in range(0, w, grid_step):
            draw.line([(x, 0), (x, h)], fill=(255, 0, 0, 35), width=1)
            # Label
            draw.text((x + 2, 2), f"{x}", fill=(255, 255, 255, 220), font=font)
            draw.text((x + 2, h - 16), f"{x}", fill=(255, 255, 255, 220), font=font)

        # Horizontal lines
        for y in range(0, h, grid_step):
            draw.line([(0, y), (w, y)], fill=(255, 0, 0, 35), width=1)
            # Label
            draw.text((2, y + 2), f"{y}", fill=(255, 255, 255, 220), font=font)
            draw.text((w - 36, y + 2), f"{y}", fill=(255, 255, 255, 220), font=font)

        # Highlight last action point if provided
        if last_action_coord:
            lx, ly = last_action_coord
            r = 12
            draw.ellipse([(lx - r, ly - r), (lx + r, ly + r)], outline=(255, 50, 50, 240), width=3)
            draw.ellipse([(lx - 2, ly - 2), (lx + 2, ly + 2)], fill=(255, 0, 0, 255))
            draw.line([(lx - 20, ly), (lx + 20, ly)], fill=(255, 50, 50, 220), width=2)
            draw.line([(lx, ly - 20), (lx, ly + 20)], fill=(255, 50, 50, 220), width=2)

        return canvas

    @staticmethod
    def to_base64_data_url(jpeg_bytes: bytes) -> str:
        b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
