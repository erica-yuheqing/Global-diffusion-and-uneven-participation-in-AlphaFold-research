"""Read-only inventory, source locks and numeric reconstruction of Figure1 exports."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import fetch_public_evidence as e
from local_recall import require,sha
from revised_country_analysis import fixed_ten,trends,annual_diffusion
from data import heatmap_data
from country_stats import gini,interval

def verify(directory):
    directory=Path(directory)
    m=json.loads((directory/'run_manifest.json').read_text())
    require(e.inventory(directory)==m['outputs'],'Output inventory/bytes changed')
    for p in m['inputs']:require(sha(Path(p['path']))==p['sha256'],'Frozen source changed')
    s=json.loads((directory/'summary.json').read_text());require(s==m['summary'],'Summary differs')
    credits=pd.read_parquet(directory/'annual_country_credits.parquet')
    for (year,group),part in credits.groupby(['year','group']):
        require(len(part)==227 and part.country_code.nunique()==227,'Country set changed')
        require(np.isclose(part.credit.sum(),part.assigned_n.iloc[0]),'Assigned credit lost')
        require(int(part.assigned_n.iloc[0]+part.unknown_n.iloc[0])==part.n.iloc[0],'Unknown coverage lost')
    require(fixed_ten(credits)==s['fixed_ten'],'Country selection not whole-period fixed')
    stack=pd.read_parquet(directory/'fixed_ten_composition.parquet')
    for year,p in stack.groupby('year'):
        require(np.isclose(p.credit.sum(),p.all_AF_studies.iloc[0]),'Stack credit loss')
        if p.all_AF_studies.iloc[0]:require(np.isclose(p.fraction.sum(),1),'Stack fraction loss')
    c=pd.read_parquet(directory/'concentration.parquet');d=pd.read_parquet(directory/'bootstrap_draws.parquet')
    for row in c.itertuples():
        for group,prefix in [('AF','af'),('C','comparator')]:
            vec=credits[(credits.year==row.year)&credits.group.eq(group)].credit.to_numpy(float)
            require(np.isclose(gini(vec),getattr(row,prefix+'_gini')),'Gini point differs')
            draws=d[(d.year==row.year)&d.group.eq(group)]
            require(len(draws)==1000 and draws.replicate.nunique()==1000,'Bootstrap replicate coverage differs')
            ci=interval(draws.gini.to_numpy())
            require(np.isclose(ci['lower'],getattr(row,prefix+'_lower')) and np.isclose(ci['upper'],getattr(row,prefix+'_upper')),'Group CI differs')
        a=d[(d.year==row.year)&d.group.eq('AF')].sort_values('replicate').gini.to_numpy()
        b=d[(d.year==row.year)&d.group.eq('C')].sort_values('replicate').gini.to_numpy()
        ci=interval(a-b)
        require(np.isclose(ci['lower'],row.delta_lower) and np.isclose(ci['upper'],row.delta_upper),'Delta CI differs')
    expected=trends(c,d);actual=pd.read_parquet(directory/'concentration_endpoint_sensitivity.parquet')
    pd.testing.assert_frame_equal(expected,actual)
    month=pd.read_parquet(directory/'monthly_diffusion.parquet')
    first=pd.read_parquet(directory/'country_first_observed.parquet')
    require(len(month)==72 and month.month.nunique()==72,'Monthly coverage differs')
    require(int(month.pre2020_countries.iloc[0]+month.new_countries.sum())==int(month.cumulative_countries.iloc[-1]),'New/cumulative chain differs')
    require(first.country_code.nunique()==int(month.cumulative_countries.iloc[-1]),'First-country endpoint differs')
    require((month.cumulative_countries.diff().dropna()>=0).all(),'Cumulative decrease')
    if (directory/'annual_diffusion_counts.parquet').is_file():
        active=pd.read_parquet(directory/'annual_country_coverage.parquet')
        pd.testing.assert_frame_equal(annual_diffusion(month,active),pd.read_parquet(directory/'annual_diffusion_counts.parquet'))
    if (directory/'raw_domestic_heatmap.parquet').is_file():
        pd.testing.assert_frame_equal(heatmap_data(credits),pd.read_parquet(directory/'raw_domestic_heatmap.parquet'))
    heat=pd.read_parquet(directory/'paired_domestic_heatmaps.parquet')
    require(len(heat)==227*6 and heat.same_study_support_both_panels.all(),'Heatmap support differs')
    annual=pd.read_parquet(directory/'annual_counts.parquet')
    require(int(annual.query('publication_year>=2020').confirmed_af.sum())==s['confirmed_AF_main'],'Total AF count differs')
    require(s['formal_revised_result'] or s['semantic_decisions_pending']==765,'Diagnostic state lost')
    print('Figure1 inventory/source/numeric reconstruction: PASS; formal:',s['formal_revised_result'])
    print('Visual/author review and residual version/coverage limitations are not certified')
    return s

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    verify(p.parse_args().directory)
if __name__=='__main__':main()
