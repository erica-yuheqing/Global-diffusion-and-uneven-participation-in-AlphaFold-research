"""Bounded schema and source audit; no private text printed or requests sent."""
from pathlib import Path
import json
import pandas as pd
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[3]
P=ROOT/'analysis/nhb_01/revision_v1/figure1_revision_final_v2'
def main():
    for name in ['annual_patterns_private.parquet','concentration.parquet','annual_counts.parquet','annual_source_coverage.parquet','fixed_ten_composition.parquet']:
        x=pd.read_parquet(P/name);print(name,len(x),list(x.columns));print(x.head(2).to_string(index=False))
    pilot=ROOT/'fulltext/pilot/human_annotation_v6/evaluation'
    report=json.loads((pilot/'pilot_150_models_vs_human_report_v6.json').read_text())
    print('PILOT',json.dumps({'reference':report['human_reference'],'metrics':{k:dict(evaluated=v['evaluated_records'],adoption=v['adoption_positive_metrics']) for k,v in report['metrics'].items()}},ensure_ascii=False))
    x=pd.read_csv(pilot/'pilot_150_models_vs_human_records_v6.csv');print('PILOT COLUMNS',len(x),list(x.columns))
    patterns=pd.read_parquet(P/'annual_patterns_private.parquet');main=patterns[patterns.year.between(2020,2025)]
    print('Main counts',main.n.sum(),'subfields',main.subfield.nunique(),'AF',main[main.group.eq('AF')].n.sum())
    aa=main[main.group.eq('AF')].groupby(['year','work_type','subfield']).n.sum();cc=main[main.group.eq('C')].groupby(['year','work_type','subfield']).n.sum().reindex(aa.index,fill_value=0)
    print('Matching unsupported',int((cc<aa).sum()),'min spare',int((cc-aa).min()))
    print('Dictionary',pd.read_parquet(ROOT/'analysis/nhb_revision_v1/baseline_features_v1/baseline_subfield_dictionary.parquet').head(2).to_string(index=False))

if __name__=='__main__':main()
