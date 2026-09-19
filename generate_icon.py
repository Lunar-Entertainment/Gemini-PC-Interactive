from PIL import Image, ImageDraw

def create_app_icon():
    # Base size 256x256
    size = (256, 256)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Rounded rectangle background with modern dark indigo gradient
    bg_color = (15, 23, 42, 255) # Slate 900
    border_color = (99, 102, 241, 200) # Indigo glow
    
    # Draw rounded card
    corner_radius = 54
    draw.rounded_rectangle([(12, 12), (244, 244)], radius=corner_radius, fill=bg_color, outline=border_color, width=4)

    # 2. Subtle inner radial glow (circles of fading cyan/indigo)
    for r, alpha in [(80, 20), (60, 35), (40, 50)]:
        glow_box = [(128 - r, 128 - r), (128 + r, 128 + r)]
        draw.ellipse(glow_box, fill=(56, 189, 248, alpha))

    # 3. Gemini Multimodal Spark Shape (Four-point star)
    # Draw central four-pointed diamond/star
    cx, cy = 128, 128
    
    # Spark polygon
    spark_points = [
        (cx, 38),          # top
        (cx + 26, cy - 26),
        (cx + 90, cy),     # right
        (cx + 26, cy + 26),
        (cx, cy + 90),     # bottom
        (cx - 26, cy + 26),
        (cx - 90, cy),     # left
        (cx - 26, cy - 26),
    ]
    # Primary cyan/blue spark fill
    draw.polygon(spark_points, fill=(56, 189, 248, 255)) # Sky cyan

    # Inner highlights (geometric gradient effect)
    top_right = [(cx, 44), (cx + 22, cy - 22), (cx + 80, cy), (cx, cy)]
    draw.polygon(top_right, fill=(129, 140, 248, 255)) # Indigo

    bottom_left = [(cx, cy + 80), (cx - 22, cy + 22), (cx - 80, cy), (cx, cy)]
    draw.polygon(bottom_left, fill=(192, 132, 252, 255)) # Purple/Violet

    center_diamond = [(cx, cy - 20), (cx + 20, cy), (cx, cy + 20), (cx - 20, cy)]
    draw.polygon(center_diamond, fill=(255, 255, 255, 240)) # Pure white central glare

    # 4. Save as .ico with all standard Windows mipmap sizes
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save("icon.ico", format="ICO", sizes=icon_sizes)
    img.save("web/icon.png", format="PNG")
    print("[OK] Generated icon.ico and web/icon.png with sizes: " + ", ".join(f"{w}x{h}" for w, h in icon_sizes))

if __name__ == "__main__":
    create_app_icon()
