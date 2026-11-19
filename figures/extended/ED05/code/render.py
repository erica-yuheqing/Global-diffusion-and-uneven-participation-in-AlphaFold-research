from release_support import release_addfont, release_font_path, release_font_family, release_executable
from pathlib import Path
import os, subprocess, tempfile
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='ed5_render_') as tmp:
    t = Path(tmp)
    (t / 'cache').mkdir()
    (t / 'fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>/System/Library/Fonts/Supplemental</dir><cachedir>' + str(t / 'cache') + '</cachedir></fontconfig>')
    env = os.environ.copy()
    env['FONTCONFIG_FILE'] = str(t / 'fonts.conf')
    subprocess.run([release_executable('pdftoppm'), '-r', '600', '-singlefile', '-png', str(ROOT / 'figures/Extended_Data_Fig5_stars.pdf'), str(ROOT / 'figures/Extended_Data_Fig5_stars_600dpi')], env=env, check=True, timeout=45)
with Image.open(ROOT / 'figures/Extended_Data_Fig5_stars_600dpi.png') as im:
    im.convert('RGB').resize((1600, round(im.height * 1600 / im.width)), Image.Resampling.LANCZOS).save(ROOT / 'figures/Extended_Data_Fig5_stars_preview.png')
    print(im.size)
