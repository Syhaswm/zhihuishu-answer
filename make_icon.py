from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

root = Path(__file__).resolve().parent
size = 256
image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 248, 248), radius=56, fill=(0, 100, 250, 255))
draw.rounded_rectangle((36, 58, 220, 198), radius=28, fill=(255, 255, 255, 255))
draw.polygon([(128, 78), (168, 132), (88, 132)], fill=(0, 100, 250, 255))
draw.rectangle((116, 132, 140, 176), fill=(0, 100, 250, 255))
font = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 42)
draw.text((128, 214), "答题", font=font, fill=(255, 255, 255, 255), anchor="mm")
icon_path = root / "app.ico"
image.save(icon_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
public = root / "ui" / "public"
public.mkdir(parents=True, exist_ok=True)
image.resize((128, 128), Image.Resampling.LANCZOS).save(public / "icon.png")
print(icon_path)
