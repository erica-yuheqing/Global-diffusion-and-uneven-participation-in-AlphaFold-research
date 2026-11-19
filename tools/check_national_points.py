"""Recalculate AF Gini/HHI/top shares from the frozen 227-country credit table.
This does not rebuild matching draws or bootstrap intervals.
"""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
p=argparse.ArgumentParser();p.add_argument('--analysis-root',type=Path,default=Path(__file__).resolve().parents[1]/'analysis_archives');a=p.parse_args();T=a.analysis_root/'01_national/tables'
d=pd.read_csv(T/'Table_S4_country_year_R_first_observation.csv',keep_default_na=False);r=pd.read_csv(T/'raw_annual_Gini.csv');out=[]
for row in r.itertuples():
 x=np.sort(d.loc[d.year==row.year,'af_credit'].to_numpy(dtype=float));n=len(x);assert n==227
 gini=float(np.sum((2*np.arange(1,n+1)-n-1)*x)/(n*x.sum()));p=x/x.sum()
 computed=[gini,float((p*p).sum()),float(p[-5:].sum()),float(p[-10:].sum())];expected=[row.af_gini,row.af_hhi,row.af_top5,row.af_top10]
 np.testing.assert_allclose(computed,expected,atol=1e-12,rtol=0)
 out.append({'year':int(row.year),'af_gini':gini,'max_abs_error':float(max(abs(np.array(computed)-expected)))})
print(json.dumps({'status':'passed','rows':out,'reference_gini_and_intervals_recomputed':False},indent=2))
