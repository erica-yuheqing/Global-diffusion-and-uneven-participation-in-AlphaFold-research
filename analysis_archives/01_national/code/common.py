"""Portable frozen-CSV inputs. No database, API, seed selection or estimation."""
from pathlib import Path
import hashlib, json
import numpy as np
import pandas as pd

BLUE='#245C86'; ORANGE='#C87425'; GRAY='#666A70'; PURPLE='#8057A3'; MUTED='#626970'
ORDER=['US','CN','JP','DE','GB','IN','FR','KR','IT','CA','BR','ES','AU','IR','RU','NL','PL','TR','CH','TW']
SPECS=['count_only','count_composition','count_composition_known_country']
ALIASES={'concentration':'source_data/S6a.csv','matching_summary':'source_data/S6b.csv',
'figure1d_top10_endpoints':'source_data/Figure1d.csv','first_observed_stage_map_source':'source_data/ED1a.csv',
'monthly_diffusion':'source_data/ED1b.csv','ed2a_attributed_composition':'source_data/ED2a.csv',
'pilot_confusion':'tables/pilot_confusion.csv','Table_S2_pilot_metrics':'tables/Table_S2_pilot_metrics.csv',
'pilot_reference_states':'tables/pilot_reference_states.csv','annual_counts':'source_data/S3a.csv',
'subfield_period_top5_other':'source_data/S3b.csv','subfield_year_top5_other':'source_data/S4b.csv',
'figure1_normalization_heatmap_source':'source_data/S5a.csv','matching_endpoint_changes':'source_data/S6c.csv',
'annual_source_coverage':'source_data/S6d.csv','annual_country_credits':'tables/Table_S4_country_year_R_first_observation.csv'}
def require(ok,message):
    if not bool(ok): raise ValueError(message)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [clean(v) for v in x]
    if isinstance(x,(np.bool_,bool)):return bool(x)
    if isinstance(x,(np.integer,int)):return int(x)
    if isinstance(x,(np.floating,float)):return float(x) if np.isfinite(x) else None
    if isinstance(x,Path):return str(x)
    return x
def dump(path,value):Path(path).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def load(out,name):
    if name=='subfield_year_top5_other':
        a=pd.read_csv(out/'inputs/source_data/S4a.csv',keep_default_na=False)
        b=pd.read_csv(out/'inputs/source_data/S4b.csv',keep_default_na=False)
        return a.merge(b[['year','display_group','AF_rate']],on=['year','display_group'],validate='one_to_one')
    return pd.read_csv(out/'inputs'/ALIASES.get(name,name),keep_default_na=False)
