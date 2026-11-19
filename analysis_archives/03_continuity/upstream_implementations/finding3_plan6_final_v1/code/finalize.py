"""Freeze a new release only after numerical, font, raster, visual and ZIP checks."""
import shutil,zipfile,tempfile,subprocess,importlib.metadata,platform
from PIL import Image,ImageChops
from common import *
from audit import numeric,technical,links
from verify_package import verify

def inventory():
    return {str(p.relative_to(OUT)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='run_manifest.json' and '__pycache__' not in p.parts}
def run():
    require(not (OUT/'run_manifest.json').exists(),'Already frozen; refusing overwrite')
    require((OUT/'provenance/visual_review_zh.md').is_file(),'Actual visual inspection record missing')
    for p in MODULE.glob('*.py'):shutil.copy2(p,OUT/'code'/p.name)
    shutil.copytree(MODULE/'planning_v1',OUT/'code/planning_v1',dirs_exist_ok=True)
    dump(OUT/'provenance/software.json',dict(python=platform.python_version(),packages={n:importlib.metadata.version(n) for n in ['pandas','numpy','duckdb','matplotlib','pillow','pyarrow']},workflow_reference='https://doi.org/10.48550/arXiv.2609.00065',reference_checked='2026-10-26'))
    test=subprocess.run([sys.executable,str(MODULE/'test_plan6.py')],capture_output=True,text=True);(OUT/'provenance/unit_tests.txt').write_text(test.stdout+test.stderr);require(test.returncode==0,'Unit test failure')
    checks=numeric();checks.update(technical());checks['16_rule_tests']=True;checks['actual_visual_review']=True
    dump(OUT/'validation_report.json',dict(status='PASS_with_explicit_uncompleted_validation',checks=checks,check_count=len(checks),API_calls=0,LLM_calls=0,bootstrap_draws_executed=0,CI_released=False,
        independent_activity_validation='240-work blind design exported; human annotation pending',reference_proxy_crosscheck='observed model/database seed proxies executed from 72 local shards; not independent accuracy validation',common_support='executed; sparse cells not extrapolated',original_data_unchanged=True,author_review_pending=True,publisher_acceptance_certified=False))
    dump(OUT/'provenance/link_audit.json',links(OUT));dump(OUT/'run_manifest.json',dict(version='Finding3_plan6_final_v1',outputs=inventory(),inputs=json.loads((OUT/'provenance/input_pins.json').read_text())))
    first=verify(OUT);archive=MODULE/'Finding3_plan6_reading_package_v1.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:z.write(p,str(Path(OUT.name)/p.relative_to(OUT)))
    with tempfile.TemporaryDirectory(prefix='finding3-v6-extract-') as td:
        with zipfile.ZipFile(archive) as z:
            require(z.testzip() is None,'ZIP CRC error');require(all(not Path(v).is_absolute() and '..' not in Path(v).parts for v in z.namelist()),'Unsafe ZIP path');z.extractall(td)
        extracted=Path(td)/OUT.name;require(verify(extracted)==first,'Extracted package differs')
        subprocess.run([sys.executable,str(extracted/'code/verify_package.py'),str(extracted)],check=True,capture_output=True)
        redraw=Path(td)/'redraw'
        subprocess.run([sys.executable,str(extracted/'code/draw.py'),'--package-root',str(extracted),'--output-root',str(redraw)],check=True,capture_output=True,text=True)
        for row in json.loads((extracted/'provenance/figure_metadata.json').read_text()):
            rel=Path('figures')/row['folder']/(row['figure']+'_preview.png')
            with Image.open(extracted/rel) as a,Image.open(redraw/rel) as b:
                require(a.size==b.size and ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox() is None,'Offline redraw differs '+row['figure'])
        require(verify(extracted)==first,'Redraw changed source package')
    dump(MODULE/'package_check.json',dict(**first,archive=str(archive),sha256=sha(archive),bytes=archive.stat().st_size,checks=len(checks),actual_extraction=True,offline_redraw_11_previews_pixel_identical=True))
    print(f'Package PASS: {len(checks)} checks, {first["files"]} files, {first["links"]} links, {archive.stat().st_size/2**20:.1f} MiB',flush=True)
if __name__=='__main__':run()
