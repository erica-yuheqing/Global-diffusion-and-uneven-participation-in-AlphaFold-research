"""Available source-field/type composition checks; no dense interaction model."""
from common import *
from analyze import standardize
import pyarrow.parquet as pq

def run():
    x=load('entry_cohort');e=load('complete_cohort');files=sorted((ROOT/'derived_tables/works').glob('*.parquet'))
    require(0<len(files)<=500,'Unexpected source work inventory')
    require('primary_field_id' in pq.ParquetFile(files[0]).schema_arrow.names,'No field metadata')
    needed=pd.DataFrame(dict(work_id=x.entry_work_id.unique()))
    with con() as c:
        c.register('needed',needed)
        field=c.execute('''SELECT n.work_id,count(DISTINCT w.primary_field_id) AS field_variants,
           CASE WHEN count(DISTINCT w.primary_field_id)=1 THEN min(w.primary_field_id) END AS broad_field
           FROM read_parquet(?) w JOIN needed n ON regexp_extract(w.work_id,'W[0-9]+',0)=n.work_id GROUP BY n.work_id''',[[str(p) for p in files]]).df()
    require(field.work_id.is_unique,'Ambiguous work rows');save('entry_broad_field_lookup',field)
    pins=json.loads((OUT/'provenance/input_pins.json').read_text());known={v['path'] for v in pins}
    for path in files:
        if str(path) not in known:pins.append(dict(path=str(path),sha256=sha(path),bytes=path.stat().st_size))
    additions=[];cells=[];weights=[]
    for mode in MODES:
        for fieldname,strata in [('type',['entry_cohort','entry_work_type']),('field',['entry_cohort','broad_field'])]:
            q=x[x['entry_'+mode].notna()&x.size_group.isin(['L','M','H'])].merge(field,left_on='entry_work_id',right_on='work_id',how='left',validate='many_to_one')
            q['outcome']=q['entry_'+mode]
            a,b,c=standardize(q,'size_group','outcome',strata,['L','M','H'],'ED6a_era_'+fieldname,mode);a['covariate_missing_N']=int(q[strata].isna().any(axis=1).sum());additions.append(a);cells.append(b);weights.append(c)
            original=e[e['entry_'+mode].notna()&e.size_group.isin(['L','M','H'])].merge(field,left_on='entry_work_id',right_on='work_id',how='left',validate='many_to_one');original['use_state']=original['entry_'+mode].astype(int).astype(str)
            for group in ['All','L','M','H']:
                z=original if group=='All' else original[original.size_group.eq(group)]
                for bound in ['lower','upper']:
                    z=z.copy();z['outcome']=z.repeat_flag.fillna(bound=='upper').astype(float)
                    a,b,c=standardize(z,'use_state','outcome',strata,['0','1'],'ED6b_era_'+fieldname+'_'+bound,mode,group);a['covariate_missing_N']=int(z[strata].isna().any(axis=1).sum());additions.append(a);cells.append(b);weights.append(c)
    prefixes=('ED6a_era_type','ED6a_era_field','ED6b_era_type','ED6b_era_field')
    for name,new in [('standardized_estimates',additions),('common_support_cells',cells),('standardization_weights',weights)]:
        old=load(name);old=old[~old.analysis.str.startswith(prefixes)];save(name,pd.concat([old,*new],ignore_index=True))
    dump(OUT/'provenance/input_pins.json',pins);dump(OUT/'provenance/composition_extensions.json',dict(status='executed',source_shards=len(files),unique_initial_works=len(needed),field_available=int(field.broad_field.notna().sum()),conflicting_fields=int(field.field_variants.gt(1).sum()),support_rule='same frozen denominator >=10; no outcomes-based selection',API_calls=0))
    print('Available type and broad-field composition checks completed',flush=True)
if __name__=='__main__':run()
