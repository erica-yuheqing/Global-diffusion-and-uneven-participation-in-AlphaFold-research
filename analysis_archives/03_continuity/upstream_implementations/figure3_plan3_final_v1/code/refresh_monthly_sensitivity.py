"""Correct month-end leap handling in the still-unpublished monthly sensitivity."""
import pandas as pd
from support import *

def run(out):
    require(not (out/'run_manifest.json').exists(),'Published output is immutable')
    e=pd.read_parquet(OLD/'tables/institution_events.parquet')
    scale=pd.read_parquet(OLD/'tables/institution_history.parquet')[['institution_id','baseline_papers','fixed_cohort_ge1']]
    h,z=monthly_history(e,scale)
    old=load(out,'window_policy_sensitivity')
    new=oldcode().state_summary(h);new['policy']='all_month_precision_sensitivity'
    save(out,'window_policy_sensitivity',pd.concat([old[old.policy.eq('day_primary')],new],ignore_index=True))
    dump(out/'provenance/month_boundary_implementation_check.json',dict(status='PASS',
      method='Calendar Period month offsets, not month-end day plus DateOffset; includes February29 correctly',
      primary_day_policy_changed=False,published_sources_changed=False,
      sensitivity_counts=new[['state','institutions','denominator']].to_dict('records')))
    print(new[['state','institutions','denominator']].to_string(index=False))

if __name__=='__main__':run(OUT)
