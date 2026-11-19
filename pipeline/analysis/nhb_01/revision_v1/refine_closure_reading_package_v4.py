"""Clarify ALL-denominator wording in a new portable release; preserve v3 bytes."""
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
from local_recall import MODULE, destination, pin, require, write_json
from fetch_public_evidence import inventory
from build_closure_reading_package_v3 import check_inventory, links_ok, checked_zip

SOURCE=MODULE/'figure1_revision_reading_package_v3'
OUT=MODULE/'figure1_revision_reading_package_v4'


def main():
    check_inventory(SOURCE);checked_zip(SOURCE.with_suffix('.zip'),SOURCE)
    out=destination(OUT);stage=Path(tempfile.mkdtemp(prefix='.closure-reading-v4-',dir=MODULE))
    for p in SOURCE.rglob('*'):
        relative=p.relative_to(SOURCE)
        if p.is_dir():(stage/relative).mkdir(exist_ok=True,parents=True)
        elif p.name!='run_manifest.json':shutil.copy2(p,stage/relative)
    results=stage/'results_zh.md';text=results.read_text()
    require(text.count('背景适格研究保留率')==1,'Expected bounded wording change')
    text=text.replace('背景适格研究保留率','全部适格研究分母的共同支持保留率')
    results.write_text(text,encoding='utf-8')
    readme=stage/'README_zh.md'
    readme.write_text(readme.read_text().replace('阅读入口 v3','阅读入口 v4'),encoding='utf-8')
    # ALL includes AF and other eligible studies. It is not identical to group C.
    checks=json.loads((stage/'release_checks.json').read_text())
    checks['presentation_clarification']='ALL retention describes all eligible denominator studies, not only screen-negative group C'
    checks['analysis_rerun_for_wording_change']=False
    checks['portable_local_links_checked']=links_ok(stage)
    (stage/'release_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    shutil.copy2(Path(__file__),stage/Path(__file__).name)
    for sub in ['tables','figures']:
        a={str(p.relative_to(SOURCE/sub)):p.read_bytes() for p in (SOURCE/sub).rglob('*') if p.is_file()}
        b={str(p.relative_to(stage/sub)):p.read_bytes() for p in (stage/sub).rglob('*') if p.is_file()}
        require(a==b,'Wording refinement cannot change any numbers or figures')
    write_json(stage/'run_manifest.json',{'schema':'figure1-evidence-closure-reading-v4','inputs':[pin(SOURCE/'run_manifest.json')],
        'outputs':inventory(stage),'executed_code':pin(Path(__file__)),
        'numeric_and_figure_bytes_identical_to_v3':True,'paid_api_calls':0})
    check_inventory(stage);require(links_ok(stage)==86,'Navigation unexpectedly changed');stage.rename(out)
    archive=out.with_suffix('.zip');require(not archive.exists(),'ZIP exists')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,Path(out.name)/p.relative_to(out))
    files=checked_zip(archive,out)
    print('Final reading package v4: PASS;',files,'files / 86 portable links;',archive.stat().st_size,'bytes')
    print('All CSVs/images unchanged; ALL-vs-screen-negative wording explicit; old releases preserved.')
    print(out/'README_zh.md');print(archive)


if __name__=='__main__':main()
