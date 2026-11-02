from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps

OUT = Path(__file__).resolve().parent
S = 2048
k = S / 1024


def sc(*pts):
    return [(x * k, y * k) for x, y in pts]


def rrect(draw, box, r, **kw):
    x0, y0, x1, y1 = [v * k for v in box]
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r * k, **kw)


grad = Image.linear_gradient("L").resize((S, S))
badge = ImageOps.colorize(grad, black="#FFF4C4", white="#FFD968").convert("RGBA")
mask = Image.new("L", (S, S), 0)
rrect(ImageDraw.Draw(mask), (0, 0, 1024, 1024), 230, fill=255)
canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
canvas.paste(badge, (0, 0), mask)

shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
rrect(ImageDraw.Draw(shadow), (250, 262, 774, 786), 70, fill=(122, 86, 0, 80))
canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(26 * k)))

frame = (250, 240, 774, 764)
d = ImageDraw.Draw(canvas)
rrect(d, frame, 70, fill="#FFFDF3")
inner = (286, 276, 738, 728)
pic = Image.new("RGBA", (S, S), (0, 0, 0, 0))
pd = ImageDraw.Draw(pic)
rrect(pd, inner, 42, fill="#FFEDA8")
pd.ellipse([v * k for v in (560, 318, 676, 434)], fill="#FFC93C")
pd.polygon(sc((286, 728), (440, 470), (600, 728)), fill="#E9B94A")
pd.polygon(sc((470, 728), (620, 540), (738, 690), (738, 728)), fill="#C58F1F")
pmask = Image.new("L", (S, S), 0)
rrect(ImageDraw.Draw(pmask), inner, 42, fill=255)
canvas.paste(pic, (0, 0), pmask)

brown = "#5A4510"
w = int(46 * k)
d = ImageDraw.Draw(canvas)
for pts in (sc((96, 420), (170, 502), (96, 584)), sc((928, 420), (854, 502), (928, 584))):
    d.line(pts, fill=brown, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=brown)

logo = canvas.resize((1024, 1024), Image.Resampling.LANCZOS)
logo.resize((512, 512), Image.Resampling.LANCZOS).save(OUT / "logo.png")
logo.save(OUT / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("logo written to", OUT)
