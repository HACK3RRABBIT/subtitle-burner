from PIL import Image, ImageDraw, ImageFont

SIZE = 512
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
radius = 112
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

img.save("logo.png")

# A wide social-preview banner (GitHub's recommended 1280x640) with the mark
# on the left and the app name + tagline on the right.
banner = Image.new("RGBA", (1280, 640), (15, 17, 21, 255))
bd = ImageDraw.Draw(banner)
mark = img.resize((340, 340), Image.LANCZOS)
mark_y = (640 - 340) // 2
banner.paste(mark, (100, mark_y), mark)

title_font = None
tagline_font = None
for candidate in (
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
):
    try:
        title_font = ImageFont.truetype(candidate, 76)
        break
    except OSError:
        continue
for candidate in (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
):
    try:
        tagline_font = ImageFont.truetype(candidate, 34)
        break
    except OSError:
        continue
if title_font is None:
    title_font = ImageFont.load_default()
if tagline_font is None:
    tagline_font = ImageFont.load_default()

text_x = 490
bd.text((text_x, 250), "Subtitle Burner", font=title_font, fill=(245, 246, 248, 255))
bd.text((text_x, 350), "Transcribe, translate, and burn subtitles - offline.",
        font=tagline_font, fill=(154, 160, 166, 255))

banner.save("social-preview.png")

print("Wrote logo.png and social-preview.png")
