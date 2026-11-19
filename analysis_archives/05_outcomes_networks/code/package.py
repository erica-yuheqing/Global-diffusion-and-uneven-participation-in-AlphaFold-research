"""Manifest, full/read-only review packages, actual extraction/hash/link tests."""
from common import *
import shutil,re,zipfile,tempfile,os
def files(root):
 return [f for f in sorted(root.rglob('*')) if f.is_file() and not any(x in ['__pycache__','scratch','.DS_Store'] for x in f.relative_to(root).parts) and f.relative_to(root).as_posix()!='manifest.json']
def manifest(root,kind):
 records=[dict(path=str(f.relative_to(root)),bytes=f.stat().st_size,sha256=sha(f),role=f.relative_to(root).parts[0]) for f in files(root)]
 dump(root/'manifest.json',{'version':'2.0','kind':kind,'generated_utc':utc(),'files':records,'self_hash':'root manifest excluded to avoid circular checksum','original_v7_changed':False,'extra_files_policy':'only scratch, __pycache__, Finder metadata excluded'})
 return records
def archive(root,kind):
 m=json.loads((root/'manifest.json').read_text());target=root.parent/(root.name+'.zip')
 with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
  for r in m['files']:z.write(root/r['path'],root.name+'/'+r['path'])
  z.write(root/'manifest.json',root.name+'/manifest.json')
 with tempfile.TemporaryDirectory(prefix='.actual_extract_v2_',dir=root.parent) as td:
  folder=Path(td)
  with zipfile.ZipFile(target) as z:
   names=z.namelist();require(len(names)==len(set(names)),'Duplicate ZIP members')
   for n in names:require((folder/n).resolve().is_relative_to(folder.resolve()),'Unsafe archive path')
   z.extractall(folder)
  extracted=folder/root.name;expected={x['path'] for x in m['files']}|{'manifest.json'};actual={str(f.relative_to(extracted)) for f in extracted.rglob('*') if f.is_file()};require(actual==expected,'ZIP missing or extra files')
  for r in m['files']:
   f=extracted/r['path'];require(f.stat().st_size==r['bytes'] and sha(f)==r['sha256'],'Extracted hash differs '+r['path'])
  links=0
  for f in extracted.rglob('*.md'):
   for href in re.findall(r'\]\(([^)]+)\)',f.read_text(errors='replace')):
    href=href.strip('<>').split('#')[0]
    if not href or href.startswith(('http:','https:','mailto:')):continue
    to=(f.parent/href).resolve();require(to.is_relative_to(extracted.resolve()) and to.exists(),'Extracted Markdown link broken '+str(f.relative_to(extracted))+' '+href);links+=1
  vals=json.loads((extracted/'manuscript/results_values.json').read_text());r=pd.read_csv(extracted/'tables/T_SI3.csv');keycount=0
  for k,v in vals.items():
   if not k.startswith(('fig6a.','fig6b.')):continue
   found=r[r.sample_id.eq(v['sample_id'])&r.group.eq(v['group'])&r.metric.eq(v['metric'])];require(len(found)==1 and np.isclose(found.estimate.iloc[0],v['estimate'],atol=1e-12),'Extracted numerical key differs '+k);keycount+=1
  # Full-package lineage links remain entirely portable after an actual extraction.
  data_links=0
  if kind=='full_reproduction':
   for f in (extracted/'source_data/panels').glob('*/lineage.json'):
    obj=json.loads(f.read_text())
    for v in obj['inputs']+obj.get('additional_inputs',[]):
     p=(f.parent/v['path']).resolve();require(p.is_relative_to(extracted.resolve()) and p.exists(),'Extracted record link broken');require(sha(p)==v['sha256'],'Extracted source hash differs');data_links+=1
 report={'status':'PASS','version':'2.0','kind':kind,'archive':target.name,'bytes':target.stat().st_size,'sha256':sha(target),'manifested_files':len(m['files']),'actual_extraction_verified':True,'extracted_hashes_verified':len(m['files']),'portable_markdown_links_verified':links,'panel_source_record_links_verified':data_links,'main_numerical_keys_checked':keycount,'api_calls':0,'original_project_data_or_code_deleted_or_overwritten':False,'verified_utc':utc()}
 dump(root.parent/(root.name+'.verification.json'),report);(root.parent/(root.name+'.zip.sha256')).write_text(report['sha256']+'  '+target.name+'\n');print(json.dumps(report,ensure_ascii=False),flush=True)
def main():
 require(json.loads((Q/'validation_report.json').read_text())['status']=='PASS','Full numerical QA not passed')
 manifest(P,'full_reproduction');archive(P,'full_reproduction')
 review=P.parent/'Scientific_Influence_review_v2.0';review.mkdir(exist_ok=True)
 allowed={'figures','tables','captions','supplementary','cases','manuscript','qa','specification','code'}
 for f in files(P):
  rel=f.relative_to(P)
  if rel.parts[0] in allowed or str(rel).startswith('source_data/panels/') or str(rel) in ['README.md','panel_index.md','analysis_config.frozen.json','environment.lock']:
   dst=review/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dst)
 banner='# 审阅包 / Reading copy\n\n本包包含图表、正文、图注、说明、汇总表及面板坐标，不含全部大表复现输入。完整复现请使用 Scientific_Influence_analysis_v2.0.zip。保留的验证报告针对完整包；本审阅包有独立解压验证。省略记录的来源路径改为full_package_path，不伪装为本包可打开的文件。\n\n'
 readme=review/'README.md';readme.write_text(banner+readme.read_text())
 # Preserve numeric coordinates/summary. Explicitly mark omitted raw record targets.
 for f in (review/'source_data/panels').glob('*/lineage.json'):
  info=json.loads(f.read_text());info['package_kind']='reading_copy_not_full_reproduction'
  for v in info['inputs']+info.get('additional_inputs',[]):
   if not (f.parent/v['path']).exists():v['full_package_path']=v.pop('path');v['availability']='full_reproduction_zip_only'
  dump(f,info)
 for f in (review/'source_data/panels').glob('*/records_index.csv'):
  z=pd.read_csv(f);z['availability']='included'
  for j,row in z.iterrows():
   if not (f.parent/row.path).exists():z.loc[j,'full_package_path']=row.path;z.loc[j,'path']=None;z.loc[j,'availability']='full_reproduction_zip_only'
  z.to_csv(f,index=False)
 for f in review.rglob('*.md'):
  def replace(match):
   href=match.group(2).strip('<>').split('#')[0]
   if not href or href.startswith(('http:','https:','mailto:')) or (f.parent/href).exists():return match.group(0)
   return match.group(1)+'（完整复现包中 / full package only）'
  f.write_text(re.sub(r'\[([^\]]+)\]\(([^)]+)\)',replace,f.read_text()))
 manifest(review,'reading_copy_not_full_reproduction');archive(review,'reading_copy_not_full_reproduction')
if __name__=='__main__':main()
