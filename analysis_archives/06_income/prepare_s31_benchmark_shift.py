"""Verify paired benchmark contrasts and prepare a compact publication table."""
from pathlib import Path
import json,hashlib,html
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'S31_updated_style'
DATA=OUT/'source_data'
order=['H','UM','LM','L']
labels={'H':'High income','UM':'Upper-middle income','LM':'Lower-middle income','L':'Low income'}
mapping=pd.read_csv(ROOT/'tables/country_income_mapping.csv',keep_default_na=False)
assert mapping.country_code.tolist()==json.loads((ROOT/'inputs/country_order.json').read_text())
raw=np.load(ROOT/'inputs/country_credits_and_joint_bootstrap.npz')
previous=pd.read_csv(ROOT/'tables/authorship_benchmark_change.csv')
rows=[];frozen={};max_error=0.
for scope in ['original_68','all_classified']:
    all_draws=np.empty((2000,4,2))
    for gi,group in enumerate(order):
        mask=mapping.income_group.eq(group).to_numpy()
        if scope=='original_68':mask &= mapping.original_68_country_sample.to_numpy(dtype=bool)
        pooled={corpus:(raw['points_'+corpus][:,mask].sum(axis=1),raw['draws_'+corpus][:,:,mask].sum(axis=2)) for corpus in ['AF','reference']}
        for ri,role in enumerate(['first','last']):
            role_index=ri+2
            point={};draw={}
            for bench,bi in [('country',0),('author',1)]:
                a,ad=pooled['AF'];r,rd=pooled['reference']
                point[bench]=a[role_index]/a[bi]-r[role_index]/r[bi]
                draw[bench]=ad[:,role_index]/ad[:,bi]-rd[:,role_index]/rd[:,bi]
            c=point['author']-point['country']
            paired=draw['author']-draw['country']
            assert np.isfinite(paired).all()
            lo,hi=np.quantile(paired,[.025,.975])
            old=previous[previous.scope.eq(scope)&previous.income_group.eq(group)&previous.role.eq(role)].iloc[0]
            err=np.max(np.abs(np.array([c,lo,hi])-old[['C','ci_low','ci_high']].to_numpy(dtype=float)))
            max_error=max(max_error,float(err));assert err<1e-12
            all_draws[:,gi,ri]=paired
            rows.append(dict(scope=scope,income_group=group,income_label=labels[group],role=role,C=c,ci_low=lo,ci_high=hi,valid_replicates=2000))
    frozen[scope]=all_draws
np.savez_compressed(DATA/'S31_paired_benchmark_shift_draws.npz',**frozen,income_order=np.array(order),role_order=np.array(['first','last']))
table=pd.DataFrame(rows)
table.to_csv(DATA/'S31_benchmark_shift_C.csv',index=False)
fmt=lambda r:f'{r.C:+.3f} [{r.ci_low:+.3f}, {r.ci_high:+.3f}]'
sections=[];plain=[]
for scope,title in [('original_68','Original scope: 68 countries'),('all_classified','Expanded scope: 213 countries and regions')]:
    section=table[table.scope.eq(scope)].set_index(['income_group','role'])
    lines=[];plain.append(title+'\nIncome group | First authorship: C [95% interval] | Last authorship: C [95% interval]')
    for group in order:
        first=fmt(section.loc[group,'first']);last=fmt(section.loc[group,'last'])
        lines.append(f'<tr><th>{labels[group]}</th><td>{first}</td><td>{last}</td></tr>')
        plain.append(f'{labels[group]} | {first} | {last}')
    sections.append(f'<h2>{title}</h2><table><thead><tr><th>Income group</th><th>First authorship<br>C [95% interval]</th><th>Last authorship<br>C [95% interval]</th></tr></thead><tbody>'+''.join(lines)+'</tbody></table>')
notes='C = ΔR(team authors) − ΔR(country participation), where ΔR = R(AF) − R(non-AF). Intervals are pointwise 95% percentile intervals calculated from 2,000 paired whole-study bootstrap replicates, preserving the original sample, standardization weights and country mapping; no multiplicity adjustment was applied. Country credits were pooled within income groups before calculating ratios. Both scopes retain 5,087 AF and 332,760 non-AF studies; outside-scope credits remain in global denominators. The original-scope low-income group comprises Ethiopia and Uganda. C measures the signed shift between benchmarks, not the reduction in the absolute AF–non-AF difference.'
title='Change in authorship representation differences between participation benchmarks'
(OUT/'Benchmark_shift_table.txt').write_text(title+'\n\n'+'\n\n'.join(plain)+'\n\n'+notes+'\n')
html_text='<!doctype html><html lang="en"><meta charset="utf-8"><title>'+title+'</title><style>body{font:15px Arial,sans-serif;color:#11151c;max-width:900px;margin:36px auto;padding:0 24px}h1{font-size:20px;font-weight:normal}h2{font-size:16px;margin-top:28px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:11px 12px;border-bottom:1px solid #e9eef4;text-align:left}thead{background:#f5f7fa}td{white-space:nowrap}tbody th{font-weight:normal}p{font-size:13px;line-height:1.5;color:#657183}</style><h1>'+title+'</h1>'+''.join(sections)+'<p>'+html.escape(notes)+'</p></html>'
(OUT/'Benchmark_shift_table.html').write_text(html_text)
prose='''Authorship representation across income groups

Replacing country participation with team-author participation shifted the AF–non-AF differences towards more positive values in the low-, lower-middle- and upper-middle-income groups, for both first and last authorship (Supplementary Fig. S31). In the original 68-country scope, the paired benchmark shifts (C) for first and last authorship were +0.222 and +0.248 in the low-income group, +0.181 and +0.148 in the lower-middle-income group, and +0.130 and +0.119 in the upper-middle-income group. In the high-income group, the shifts were negative (−0.043 and −0.046). All corresponding pointwise 95% paired bootstrap intervals excluded zero. The direction of these shifts was retained when classification was extended to 213 countries and regions, using the same research sample. A positive C describes a shift in the signed difference and does not necessarily indicate a smaller absolute difference. Estimates for the original low-income group warrant particular caution because it includes only Ethiopia and Uganda. Exact estimates and intervals are reported in the accompanying table.
'''
(OUT/'Results_for_Note2_authorship.txt').write_text(prose)
verification={'paired_replicates':2000,'contrasts_verified':len(rows),'maximum_error_against_original_paired_C_table':max_error,'income_order_top_to_bottom':order,'pairing':'Within each shared whole-study replicate, C = [R_AF(author) - R_nonAF(author)] - [R_AF(country) - R_nonAF(country)].','draw_array_shape_per_scope':[2000,4,2],'inputs_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'inputs/country_credits_and_joint_bootstrap.npz',ROOT/'tables/country_income_mapping.csv',ROOT/'tables/authorship_benchmark_change.csv']}}
(OUT/'benchmark_shift_verification.json').write_text(json.dumps(verification,indent=2))
print(json.dumps({'contrasts_verified':len(rows),'maximum_error':max_error,'table':str(OUT/'Benchmark_shift_table.html')},indent=2))
