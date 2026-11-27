"""Draw the OM MAVA Updater icon: blue clapper board, MAVA mark (ring + hex nut) cut out of the body, transparent
background. Same shapes as plans/261105-1049-mava-updater/updater-icon.svg.

  python make_icon.py <out.iconset>        every size macOS asks for
  python make_icon.py --png <file> <px>    one PNG (the window header uses mark.png)
Needs Pillow."""
import math, os, sys
from PIL import Image, ImageDraw

ORANGE = (38, 132, 255, 255)     # OM: blue, so it is not mistaken for MAVA Updater (orange)
# geometry in a 100-unit box (8 % margin all round, as macOS icons have)
BODY = (10, 45, 90, 88)          # x0, y0, x1, y1
BODY_R = 8
ARM = (10, 30, 90, 42)           # closed position, just above the body
ARM_R = 4
ARM_OPEN = 10                    # degrees, hinged at the arm's bottom-left corner
CX, CY = 50, 66.5                  # MAVA mark centre
RING_OUT, RING_IN = 17, 13       # ring radii
HEX_R, HOLE_R = 9.5, 3.6         # hex nut circumradius, its hole


def draw(size=1024, ss=4):
    S = size * ss
    k = S / 100
    box = lambda b: [b[0] * k, b[1] * k, b[2] * k, b[3] * k]
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle(box(BODY), radius=BODY_R * k, fill=ORANGE)
    arm = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(arm).rounded_rectangle(box(ARM), radius=ARM_R * k, fill=ORANGE)
    im.alpha_composite(arm.rotate(ARM_OPEN, resample=Image.BICUBIC, center=(ARM[0] * k, ARM[3] * k)))
    hole = Image.new("L", (S, S), 0)
    h = ImageDraw.Draw(hole)
    circle = lambda r, fill: h.ellipse([(CX - r) * k, (CY - r) * k, (CX + r) * k, (CY + r) * k], fill=fill)
    circle(RING_OUT, 255)
    circle(RING_IN, 0)
    h.polygon([((CX + HEX_R * math.sin(math.radians(60 * i))) * k, (CY - HEX_R * math.cos(math.radians(60 * i))) * k)
               for i in range(6)], fill=255)
    circle(HOLE_R, 0)
    alpha = im.getchannel("A")
    alpha.paste(0, mask=hole)
    im.putalpha(alpha)
    return im.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    if sys.argv[1] == "--png":
        draw(int(sys.argv[3])).save(sys.argv[2])
        sys.exit()
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for s in (16, 32, 128, 256, 512):
        draw(s).save(os.path.join(out, f"icon_{s}x{s}.png"))
        draw(s * 2).save(os.path.join(out, f"icon_{s}x{s}@2x.png"))
