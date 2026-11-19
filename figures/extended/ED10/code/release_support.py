"""Portable plotting support; does not change data, estimates or sampling."""
from pathlib import Path
import os, shutil

def release_font_path(requested):
    p=Path(str(requested))
    if p.is_file(): return str(p)
    from matplotlib import font_manager
    bold='bold' in str(requested).lower()
    return font_manager.findfont(font_manager.FontProperties(family='DejaVu Sans',weight='bold' if bold else 'normal'),fallback_to_default=True)
def release_addfont(requested):
    from matplotlib import font_manager
    return font_manager.fontManager.addfont(release_font_path(requested))
def release_font_family():
    from matplotlib import font_manager
    return 'Arial' if any(f.name=='Arial' for f in font_manager.fontManager.ttflist) else 'DejaVu Sans'
def release_executable(name):
    path=os.environ.get(name.upper()) or shutil.which(name)
    if not path: raise RuntimeError(f'{name} is required. Install Poppler and put it on PATH, or set {name.upper()} to its executable.')
    return path
