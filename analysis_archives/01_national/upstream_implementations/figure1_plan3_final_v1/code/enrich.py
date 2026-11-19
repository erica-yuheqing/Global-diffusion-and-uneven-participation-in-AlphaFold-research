"""Audit production/pilot correspondence and bibliography without new requests."""
import re,subprocess
from common import *
from prepare import evaluate_pilot,pin

def run(out):
    pins=[];meta=ROOT/'fulltext/production/final_database_v2/af_research_database_final_summary_v2.json';md=json.loads(meta.read_text())
    p=ROOT/'fulltext/production/final_database_v2/af_research_database_final_v2.csv'
    require(sha(p)==md['outputs'][p.name]['sha256'],'Final database bytes differ');pins.append(pin(p))
    cols=['work_id','af_use_label','adoption_eligible','decision_route','source_route','selected_source_models','primary_label']
    production=pd.read_csv(p,usecols=cols,keep_default_na=False);require(len(production)==29127 and production.work_id.is_unique,'Initial candidate scope differs')
    save(out,'initial_candidate_dispositions',production.groupby(['af_use_label','adoption_eligible']).size().reset_index(name='candidate_work_records'))
    pilot=load(out,'pilot_comparison_records');x=pilot.merge(production.rename(columns={c:'production_'+c for c in cols if c!='work_id'}),on='work_id',how='left',validate='one_to_one')
    require(x.production_af_use_label.notna().all(),'Pilot/final overlap incomplete')
    rows,metric=evaluate_pilot(x,'production')
    save(out,'pilot_production_correspondence',x[['review_id','work_id','reference_route','reference_status','metric_eligible','human_af_use_label','human_adoption_eligible']+['production_'+c for c in cols if c!='work_id']])
    prior=load(out,'pilot_confusion');save(out,'pilot_confusion',pd.concat([prior,pd.DataFrame(rows)],ignore_index=True))
    prior=load(out,'Table_S2_pilot_metrics');save(out,'Table_S2_pilot_metrics',pd.concat([prior,pd.DataFrame([metric])],ignore_index=True))
    save(out,'pilot_production_routes',x.groupby(['production_decision_route','production_source_route','production_selected_source_models']).size().reset_index(name='n'))
    manifest=ROOT/'fulltext/production/model_inputs_v1/full_model_inputs.meta.json';pins.append(pin(manifest));packet=json.loads(manifest.read_text())
    require(packet['record_count']==29127 and sum(packet['evidence_tiers'].values())==29127,'Initial packet evidence tier totals differ')
    save(out,'initial_evidence_tiers',pd.DataFrame([dict(evidence_tier=k,candidate_work_records=v) for k,v in packet['evidence_tiers'].items()]))
    seeds=ROOT/'config/alphafold_seed_works.json';pins.append(pin(seeds));seedconfig=json.loads(seeds.read_text());require(len(seedconfig['seeds'])==4,'Initial seed count differs')
    refs=[('AF2','Jumper, J. et al.','Highly accurate protein structure prediction with AlphaFold',2021,'Nature 596, 583–589','10.1038/s41586-021-03819-2','AlphaFold2_2021.pdf'),
      ('AlphaFold-Multimer','Evans, R. et al.','Protein complex prediction with AlphaFold-Multimer',2021,'bioRxiv preprint','10.1101/2021.10.04.463034',None),
      ('AFDB','Varadi, M. et al.','AlphaFold Protein Structure Database: massively expanding the structural coverage of protein-sequence space with high-accuracy models',2022,'Nucleic Acids Research 50(D1), D439–D444','10.1093/nar/gkab1061','AF database_2022.pdf'),
      ('AF3','Abramson, J. et al.','Accurate structure prediction of biomolecular interactions with AlphaFold 3',2024,'Nature 630, 493–500','10.1038/s41586-024-07487-w','AlphaFold3_2024.pdf')]
    refsout=[]
    for seed,authors,title,year,venue,doi,pdf in refs:
        if pdf:
            path=ROOT/'Landmark papers_AlphaFold'/pdf;text=subprocess.run(['pdftotext','-f','1','-l','1',str(path),'-'],capture_output=True,text=True,check=True).stdout
            require(doi in text,'Seed DOI absent from local first page');pins.append(pin(path));status='DOI/title checked against archived PDF first page'
        else:require(any(doi in x['dois'] for x in seedconfig['seeds']),'Seed DOI not in original config');status='Title/DOI from archived initial seed config; no new metadata request'
        refsout.append(dict(seed=seed,authors=authors,title=title,year=year,venue=venue,doi=doi,url='https://doi.org/'+doi,metadata_status=status))
    save(out,'Table_S1_seed_references',pd.DataFrame(refsout))
    # Milestone publication/server labels are user-specified month boundaries, not code-release dates.
    save(out,'Table_S1_milestones',pd.DataFrame([['AF2 code + AFDB','2021-07','User plan month boundary; not AFDB journal publication date'],['AF3 publication/server','2024-05','Not AF3 code release'],['Pre-AF2 era','2020-01 to 2021-06','Main study-era start; pre2020 first-observation retained separately']],columns=['label','month','interpretation']))
    d=load(out,'matching_draws');m=load(out,'matching_summary');examples={('count_only',2021):.0260,('count_only',2025):.0247,('count_composition',2021):.0168,('count_composition',2025):.0194};rows=[]
    for (spec,year),example in examples.items():
        gaps=d[d.spec.eq(spec)&d.year.eq(year)].gap;r=m[m.spec.eq(spec)&m.year.eq(year)].iloc[0]
        rows.append(dict(spec=spec,year=year,document_example=example,local_reconstruction=r.point,difference=r.point-example,
          MC_standard_error_of_mean=gaps.std(ddof=1)/np.sqrt(len(gaps)),same_original_seed_confirmed=False,
          reconciliation_status='Original handoff not supplied; values not forced to document examples'))
    save(out,'document_matching_value_comparison',pd.DataFrame(rows));dump(out/'provenance/additional_input_pins.json',pins)
    dump(out/'provenance/pilot_correspondence_audit.json',dict(pilot_works=150,overlap_original_production=150,evaluated_reference=122,
      production_joint_use_metrics=metric,reference_independence_confirmed=False,out_of_sample_validation=False,
      caution='Production overlap is not an independent holdout; reference labels and tuning may have informed workflow. Historical ensemble and final production comparisons reported separately.'))
    print('Production/pilot linkage audited; original packet tiers and four seed references retained. Production pilot precision/recall:',metric['precision'],metric['recall'],flush=True)

if __name__=='__main__':run(OUT)
