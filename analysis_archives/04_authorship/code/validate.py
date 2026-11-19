"""Offline typed-data, draw, link and exported-file verification, without API access."""
from common import *
from scipy import sparse
import subprocess,re,urllib.parse,sys
from PIL import Image
def check_links():
    bad=[];count=0
    # Immutable historical documents are source archives, not current navigation.
    files=[ROOT/'README_zh.md']+list((ROOT/'manuscript').glob('*.md'))+list((ROOT/'source_data').glob('*.md'))+list((ROOT/'code').glob('*.md'))
    for f in files:
      for raw in re.findall(r'!?\[[^\]]*\]\(([^\n]+?)\)',f.read_text()):
        target=raw.strip().strip('<>');target=urllib.parse.unquote(target.split('#')[0])
        if not target or re.match(r'https?://|mailto:',target):continue
        count+=1;p=(f.parent/target).resolve()
        if target.startswith('/') or not p.is_relative_to(ROOT) or not p.exists():bad.append(dict(file=str(f.relative_to(ROOT)),target=target))
    require(not bad,'Invalid current reading links: '+str(bad));return dict(checked_links=count,active_markdown=len(files),broken=bad,archive_scope='inputs/handoff* original historical documents intentionally byte-preserved and outside current-navigation checks')
def main():
    checks={};extra={}
    if not (ROOT/'provenance/validation_summary.json').exists():dump(ROOT/'provenance/validation_summary.json',dict(status='RUNNING'))
    def ck(k,v):require(v,k);checks[k]=True
    m=norm('analysis_members.parquet');meta=json.loads((ROOT/'inputs/normalized/feature_metadata.json').read_text());X=sparse.load_npz(ROOT/'inputs/normalized/feature_matrix.npz')
    ck('strict_distinct_author_sample',m.first_id.ne(m.last_id).all() and m.study_id.is_unique)
    ck('joint_vector_row_order',len(m)==X.shape[0] and np.array_equal(m.row_index,np.arange(len(m))))
    from bootstrap import ratios,pair_shares
    # Recompute every principal point estimate from the packaged study-level vectors.
    R=pd.read_parquet(ROOT/'tables/strict_main_R.parquet');P=pd.read_parquet(ROOT/'tables/strict_main_pairings.parquet');S=pd.read_parquet(ROOT/'tables/strict_main_structure.parquet')
    for cp in CORPORA:
      for setting in ['raw_full','common_raw','standardized']:
        w=m.corpus.eq(cp).to_numpy(float)
        if setting=='common_raw':w*=m.supported
        if setting=='standardized':w*=m.weight
        pool=np.asarray(X.T@w).ravel();r=ratios(pool[None,:],meta)[0];ps=pair_shares(pool[None,:],meta)
        for b,bench in enumerate(['country','author']):
          for j,role in enumerate(['first','last']):
            t=R[R.corpus.eq(cp)&R.setting.eq(setting)&R.benchmark.eq(bench)&R.role.eq(role)].set_index('entity_id').loc[meta['entities']];ck(f'point_R_{cp}_{setting}_{bench}_{role}',np.allclose(t.R,r[b,j],equal_nan=True,atol=1e-11))
        t=P[P.corpus.eq(cp)&P.setting.eq(setting)].set_index(['first_group','last_group']).reindex(pd.MultiIndex.from_product([GROUPS,GROUPS]));ck(f'point_pair_{cp}_{setting}',np.allclose(t.observed_share,ps['observed_group'][0],atol=1e-11) and np.allclose(t.expected_share,ps['expected_group'][0],atol=1e-11))
        t=S[S.corpus.eq(cp)&S.setting.eq(setting)].set_index('category').loc[meta['structure_categories']];ck(f'point_structure_{cp}_{setting}',np.allclose(t.share,ps['structure'][0],atol=1e-11))
    pins=json.loads((ROOT/'provenance/input_pins.json').read_text());verified=0;orig=0;unavailable=[]
    for pin in pins:
      p=ROOT/pin['copy'];ck('input_copy_'+str(verified),p.is_file() and sha(p)==pin['sha256']);verified+=1
      source=Path(pin['original'])
      if source.is_file():ck('original_unmodified_'+str(orig),sha(source)==pin['sha256']);orig+=1
      else:unavailable.append(str(source))
    extra['inputs']=dict(packaged_pins_verified=verified,original_files_rechecked_on_this_host=orig,unavailable_originals=unavailable)
    raw_verified=0;raw_missing=[]
    for pin in json.loads((ROOT/'provenance/external_raw_input_manifest.json').read_text()):
      source=Path(pin['path'])
      if source.is_file():ck('upstream_raw_unmodified_'+str(raw_verified),sha(source)==pin['sha256']);raw_verified+=1
      else:raw_missing.append(str(source))
    extra['upstream_raw']=dict(original_files_rechecked=raw_verified,unavailable_on_this_host=raw_missing,scope='optional original preservation audit; packaged normalized snapshots are sufficient for analysis replay')
    registry=json.loads((ROOT/'provenance/figure_registry.json').read_text());exports=[]
    for row in registry:
      pdf=ROOT/row['pdf'];info=subprocess.run(['/opt/homebrew/bin/pdfinfo',str(pdf)],check=True,capture_output=True,text=True).stdout;pages=int(re.search(r'Pages:\s+(\d+)',info)[1]);ck('PDF_pages_'+row['figure_id'],pages==row['pages'])
      fonts=subprocess.run(['/opt/homebrew/bin/pdffonts',str(pdf)],check=True,capture_output=True,text=True).stdout;flags=re.findall(r'\s(yes|no)\s+(yes|no)\s+(yes|no)\s+\d+\s+\d+\s*$',fonts,re.M);ck('fonts_embedded_'+row['figure_id'],bool(flags) and all(f[0]=='yes' for f in flags) and 'Type 3' not in fonts)
      item=dict(figure_id=row['figure_id'],pdf_pages=pages,fonts_embedded=True,pdfinfo=info,pdffonts=fonts)
      if row['main']:
        name=row['figure_id'];svg=ROOT/'figures'/(name+'.svg');ck('editable_SVG_'+name,'<text' in svg.read_text());wm=re.search(r'Page size:\s+([\d.]+) x ([\d.]+)',info);ck('183mm_width_'+name,abs(float(wm[1])*25.4/72-183)<.02)
        item['rasters']=[]
        for suffix in ['_600dpi.png','_600dpi.tiff']:
          path=ROOT/'figures'/(name+suffix)
          with Image.open(path) as im:
            dpi=tuple(float(x) for x in im.info.get('dpi',(0,0)));ck('RGB_'+name+suffix,im.mode=='RGB');ck('native_600dpi_'+name+suffix,min(dpi)>599 and abs(im.width-183/25.4*600)<=1);item['rasters'].append(dict(path=str(path.relative_to(ROOT)),mode=im.mode,pixels=im.size,dpi=dpi,compression=im.info.get('compression','lossless_png')))
      exports.append(item)
    extra['export_metadata']=exports;extra['navigation']=check_links()
    ck('table_groups_7',len(pd.read_csv(ROOT/'source_data/table_registry.csv').table_group.unique())==7);ck('six_notes',(ROOT/'manuscript/supplementary_notes_zh_en.md').read_text().count('## Note ')==6)
    dump(ROOT/'provenance/validation_summary.json',dict(status='PASS',check_count=len(checks),checks=checks,details=extra,scope='input preservation, exact principal-point reconstruction, metadata and current navigation; not semantic gold or publisher acceptance'))
    print('Offline validation PASS:',len(checks),'checks;',extra['navigation']['checked_links'],'current links',flush=True)
if __name__=='__main__':main()
