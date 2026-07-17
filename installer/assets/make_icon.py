from PIL import Image, ImageDraw

SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

bg_top = (37, 99, 235, 255)
bg_bottom = (29, 78, 216, 255)
for y in range(SIZE):
    t = y / SIZE
    r = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
    g = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
    b = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)
    d.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

mask = Image.new("L", (SIZE, SIZE), 0)
mask_draw = ImageDraw.Draw(mask)
radius = 56
mask_draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=radius, fill=255)
rounded = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
rounded.paste(img, (0, 0), mask)
img = rounded
d = ImageDraw.Draw(img)

# Play triangle
tri_cx, tri_cy = SIZE * 0.42, SIZE * 0.40
tri_w, tri_h = SIZE * 0.26, SIZE * 0.30
d.polygon(
    [
        (tri_cx - tri_w / 2, tri_cy - tri_h / 2),
        (tri_cx - tri_w / 2, tri_cy + tri_h / 2),
        (tri_cx + tri_w / 2, tri_cy),
    ],
    fill=(255, 255, 255, 235),
)

# Subtitle bars
bar_h = SIZE * 0.075
bar_r = bar_h / 2
bars = [
    (SIZE * 0.16, SIZE * 0.66, SIZE * 0.84),
    (SIZE * 0.16, SIZE * 0.80, SIZE * 0.62),
]
for x0, y0, x1 in bars:
    d.rounded_rectangle([x0, y0, x1, y0 + bar_h], radius=bar_r, fill=(255, 255, 255, 235))

img.save("icon_source.png")

sizes = [16, 24, 32, 48, 64, 128, 256]
imgs = [img.resize((s, s), Image.LANCZOS) for s in sizes]
imgs[0].save("icon.ico", sizes=[(s, s) for s in sizes])
print("Wrote icon.ico and icon_source.png")
