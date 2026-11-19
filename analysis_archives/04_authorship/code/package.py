"""Release archive with actual extraction, hashes, relative links and offline replay QA."""
from common import *
import argparse,zipfile,tempfile,subprocess,os,unittest,importlib.util
def stream_sha(stream):
    h=hashlib.sha256()
    for b in iter(lambda:stream.read(1048576),b''):h.update(b)
    return h.hexdigest()
def files():
    pinned={p['copy'] for p in json.loads((ROOT/'provenance/input_pins.json').read_text())}
    out=[]
    for p in sorted(ROOT.rglob('*')):
      if not p.is_file():continue
      r=p.relative_to(ROOT)
      if str(r) in pinned:out.append(p);continue
      if p==ROOT/'manifest.json' or r.parts[0]=='scratch' or '__pycache__' in r.parts or p.name=='.DS_Store':continue
      require(not p.is_symlink(),'No archive symlink inputs');out.append(p)
    return out
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,required=True);a=ap.parse_args();archive=a.archive.expanduser().resolve();require(not archive.exists(),'Archive already exists; choose a new version')
    # Remove only redundant temporary .npy mirrors created by this run, after
    # proving that their compressed archival members have identical bytes.
    mirrors=[]
    for cp in CORPORA:
      for setting in ['raw_full','standardized']:
        tmp=ROOT/'scratch'/f'country_draws_{cp}_{setting}.npy';stored=ROOT/'draws'/f'country_pair_{cp}_{setting}.npz'
        if tmp.exists():
          before=sha(tmp)
          with zipfile.ZipFile(stored) as z:
            with z.open('joint_country_O_E.npy') as f:after=stream_sha(f)
          require(before==after,'Compressed country draws do not match temporary mirror')
          mirrors.append(dict(temporary_file=str(tmp.relative_to(ROOT)),archival_file=str(stored.relative_to(ROOT)),sha256=before,lossless_identical=True));tmp.unlink()
    dump(ROOT/'provenance/temporary_draw_archive_audit.json',dict(status='PASS',mirrors=mirrors,scope='only this run redundant scratch mirrors removed after exact byte identity; no source/project data or historical code removed'))
    dump(ROOT/'manifest.json',dict(status='BUILDING'))
    env=dict(os.environ,OPENBLAS_NUM_THREADS='2',VECLIB_MAXIMUM_THREADS='2')
    spec=importlib.util.spec_from_file_location('release_tests',ROOT/'code/tests.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);r=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(mod));require(r.wasSuccessful(),'Release regression tests failed');dump(ROOT/'provenance/regression_tests.json',dict(status='PASS',tests_run=r.testsRun,failures=[],errors=[]))
    subprocess.run([sys.executable,str(ROOT/'code/validate.py')],check=True,env=env)
    inventory=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in files()];dump(ROOT/'manifest.json',dict(status='PASS',version='Finding4_v7_Figure4_Figure5_complete_v1',date='2026-10-30',files=inventory,excluded=['scratch/','__pycache__/','unmanifested Finder metadata'],manifest_self_excluded=True))
    print('Writing archive:',archive,'files',len(inventory)+1,flush=True)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
      for i,p in enumerate(files()+[ROOT/'manifest.json'],1):
        compressed=p.suffix.lower() in {'.npz','.parquet','.png','.jpg','.jpeg','.tiff','.gz','.pdf'}
        z.write(p,arcname=str(Path(ROOT.name)/p.relative_to(ROOT)),compress_type=zipfile.ZIP_STORED if compressed else zipfile.ZIP_DEFLATED)
        if i%100==0:print('Archived',i,'files',flush=True)
    with zipfile.ZipFile(archive) as z:
      require(z.testzip() is None,'ZIP CRC failed');names=z.namelist();require(all(not Path(n).is_absolute() and '..' not in Path(n).parts and Path(n).parts[0]==ROOT.name for n in names),'Unsafe archive path');print('CRC PASS; extracting actual archive for full verification',flush=True)
      with tempfile.TemporaryDirectory(prefix='.finding4-v7-zip-check-',dir=ROOT.parent) as tmp:
        z.extractall(tmp);extracted=Path(tmp)/ROOT.name;manifest=json.loads((extracted/'manifest.json').read_text())
        for record in manifest['files']:require(sha(extracted/record['path'])==record['sha256'],'Extracted hash mismatch '+record['path'])
        v=subprocess.run([sys.executable,str(extracted/'code/replay.py')],check=True,env=env,capture_output=True,text=True)
        # Verification itself must not change any delivered snapshot bytes.
        for record in manifest['files']:require(sha(extracted/record['path'])==record['sha256'],'Offline verification changed snapshot '+record['path'])
        validation=json.loads((extracted/'provenance/validation_summary.json').read_text())
        result=dict(status='PASS',date='2026-10-30',archive=str(archive),archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,files=len(names),all_CRC_valid=True,actual_extraction=True,all_manifest_hashes_match=True,offline_regression_and_point_reconstruction=True,offline_validation_stdout=v.stdout,offline_test_output=v.stderr,validation_checks=validation['check_count'],current_reading_links=validation['details']['navigation']['checked_links'],current_links_broken=0,after_validation_snapshot_unchanged=True,source_preservation=validation['details']['inputs'],upstream_source_preservation=validation['details']['upstream_raw'],temporary_extraction_copy_cleaned_after_verification=True)
    dump(archive.with_suffix('.verification.json'),result);print('ZIP EXTRACTION / HASHES / OFFLINE REPLAY / LINKS PASS:',archive,flush=True)
if __name__=='__main__':
    import sys
    main()
