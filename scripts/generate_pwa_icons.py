"""Generate multi-resolution PWA icons and favicons from source icon."""
import os
from PIL import Image

def generate_icons():
    source_path = os.path.join("static", "icona1.png")
    output_dir = os.path.join("static", "icons")
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(source_path):
        print(f"Error: Source image not found at {source_path}")
        return

    master = Image.open(source_path).convert("RGBA")

    # Standard icons
    sizes = {
        "icon-192x192.png": (192, 192),
        "icon-512x512.png": (512, 512),
        "apple-touch-icon.png": (180, 180),
        "favicon-32x32.png": (32, 32),
        "favicon-16x16.png": (16, 16),
    }

    for filename, size in sizes.items():
        resized = master.resize(size, Image.Resampling.LANCZOS)
        out_path = os.path.join(output_dir, filename)
        resized.save(out_path, "PNG", optimize=True)
        print(f"Generated: {out_path} ({size[0]}x{size[1]})")

    # Maskable icon (needs safe margin ~10-15% padding so circular masks don't clip icon edges)
    maskable_size = (512, 512)
    inner_size = (int(512 * 0.75), int(512 * 0.75))
    maskable_img = Image.new("RGBA", maskable_size, (35, 35, 46, 255)) # Dark theme background #23232e
    inner_icon = master.resize(inner_size, Image.Resampling.LANCZOS)
    offset = ((512 - inner_size[0]) // 2, (512 - inner_size[1]) // 2)
    maskable_img.paste(inner_icon, offset, mask=inner_icon)
    maskable_out = os.path.join(output_dir, "icon-maskable-512x512.png")
    maskable_img.save(maskable_out, "PNG", optimize=True)
    print(f"Generated maskable: {maskable_out} ({maskable_size[0]}x{maskable_size[1]})")

if __name__ == "__main__":
    generate_icons()
