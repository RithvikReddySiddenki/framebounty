"""Small repeated-watermark previews; screenshots/removal remain possible."""
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps
from fastapi import HTTPException
from fastapi.responses import Response
from .media import LocalStorage


def owns_original(item, wallet):
    return wallet == item.wallet or item.state in {"accepted", "fixture_accepted"}


def preview_response(item, index=0):
    frames = item.findings.get("frames", [])
    if index < 0 or index >= len(frames):
        raise HTTPException(409, "Preview is not ready; verification is still processing")
    path = LocalStorage().path(frames[index]["key"])
    if not path.is_file(): raise HTTPException(404, "Preview unavailable")
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((480, 480))
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        font = ImageFont.load_default(size=17)
        label = "FrameBounty - UNPAID PREVIEW"
        for y in range(-20, image.height, 65):
            for x in range(-100, image.width, 230):
                draw.rectangle((x, y, x + 270, y + 27), fill=(0, 0, 0, 120))
                draw.text((x + 4, y + 4), label, font=font, fill=(255, 255, 255, 215))
        image = Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")
        out = BytesIO(); image.save(out, "JPEG", quality=55)
    return Response(out.getvalue(), media_type="image/jpeg", headers={
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
