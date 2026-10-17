from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parents[1]
source = root / 'src' / 'donathon' / 'assets' / 'logo_icon.png'
output = root / 'buildtools' / 'DonathonTimer.ico'
with Image.open(source) as src:
    image = src.convert('RGBA')
    image.save(output, format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(output)
