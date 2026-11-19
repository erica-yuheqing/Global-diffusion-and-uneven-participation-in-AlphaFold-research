"""Reconstruct approved study-level opportunities and baseline-only institution groups."""
import argparse
import shutil
import time
from support import *

def build(out):
    start = time.monotonic()
    audit = []
    def flow(stage, unit, n, note):
        audit.append(dict(stage=stage, unit=unit, N=int(n), note=note))
    def cp(c, query, name):
        c.execute(f'COPY ({query}) TO {lit(out/"tables"/(name+".parquet"))} (FORMAT PARQUET, COMPRESSION ZSTD)')
    with connect(out) as c:
        c.execute(f'''CREATE TEMP TABLE raw_studies AS SELECT study_id,annual_representative_work_id AS work_id,
          publication_year AS year,publication_date,representative_date_status,
          coalesce(primary_subfield_id,'Unknown subfield') AS field,work_type AS document_type,
          confirmed_af,possible_af,af_use_label,adoption_eligible,screen_negative,
          CASE WHEN confirmed_af THEN 1
            WHEN NOT coalesce(possible_af,FALSE) AND (screen_negative OR af_use_label='no' OR adoption_eligible='no') THEN 0
            ELSE -1 END AS z,
          member_work_records,deduplication_status,representative_selection_status
          FROM read_parquet({lit(F1/'derived_study_records.parquet')})''')
        n = c.execute('SELECT count(*) FROM raw_studies').fetchone()[0]
        flow('01_frozen_studies', 'study', n, 'Approved study units; no new merges')
        require(c.execute('SELECT count(*)-count(DISTINCT study_id) FROM raw_studies').fetchone()[0] == 0, 'Duplicate study identity')
        c.execute(f'''CREATE TEMP TABLE links AS SELECT DISTINCT s.study_id,i.institution_id,i.country_code
          FROM raw_studies s JOIN read_parquet({lit(UP/'work_institutions.parquet')}) i USING(work_id)
          WHERE i.institution_id IS NOT NULL''')
        c.execute(f'''CREATE TEMP TABLE memberships AS SELECT DISTINCT s.study_id,i.institution_id
          FROM raw_studies s JOIN read_parquet({lit(UP/'work_institution_membership.parquet')}) i USING(work_id)
          WHERE i.institution_id IS NOT NULL''')
        c.execute(f'''CREATE TEMP TABLE countries AS SELECT DISTINCT s.study_id,k.country_code
          FROM raw_studies s JOIN read_parquet({lit(UP/'work_countries.parquet')}) k USING(work_id)
          WHERE k.country_code IS NOT NULL''')
        c.execute('''CREATE TEMP TABLE country_sets AS SELECT study_id,string_agg(country_code,'|' ORDER BY country_code) AS country_set,
          count(*) AS n_countries FROM countries GROUP BY study_id''')
        c.execute('''CREATE TEMP TABLE inst_counts AS SELECT study_id,count(*) AS n_institutions
          FROM memberships GROUP BY study_id''')
        # Common field support is baseline-defined, not selected using AF outcomes.
        c.execute('CREATE TEMP TABLE baseline_fields AS SELECT DISTINCT field FROM raw_studies WHERE year BETWEEN 2015 AND 2019')
        cp(c, '''SELECT field,year,count(*) AS studies,count(*) FILTER(WHERE z=1) AS AF_studies,
          field IN (SELECT field FROM baseline_fields) AS shared_baseline_field_scope
          FROM raw_studies GROUP BY ALL ORDER BY field,year''', 'field_scope_audit')
        # All frozen eligible fields are retained: before/after field-scope differences are audited.
        # A missing baseline observation in a field is not evidence it was excluded from collection.
        c.execute('''CREATE TEMP TABLE studies AS SELECT s.*,k.country_set,coalesce(k.n_countries,0) AS n_countries,
          coalesce(i.n_institutions,0) AS n_institutions,
          'year_observed; exact_month_day_precision_not_certified' AS date_precision,
          CASE WHEN i.n_institutions IS NULL THEN 'institution_unattributed'
               WHEN k.n_countries IS NULL THEN 'country_unattributed' ELSE 'known_year_and_attribution' END AS metadata_quality
          FROM raw_studies s LEFT JOIN country_sets k USING(study_id) LEFT JOIN inst_counts i USING(study_id)''')
        c.execute('DROP TABLE raw_studies; DROP TABLE country_sets; DROP TABLE inst_counts; DROP TABLE baseline_fields')
        cp(c, 'SELECT * FROM studies', 'studies')
        cp(c, '''SELECT year,z,metadata_quality,count(*) AS N FROM studies GROUP BY ALL ORDER BY 1,2,3''', 'study_label_attribution_audit')
        cp(c, '''SELECT representative_date_status,count(*) AS studies FROM studies GROUP BY ALL''', 'date_precision_audit')
        # Baseline output remains integer; multi-country appearance does not inflate Vi.
        c.execute('''CREATE TEMP TABLE base_counts AS SELECT m.institution_id,count(DISTINCT s.study_id)::BIGINT AS V_i
          FROM studies s JOIN memberships m USING(study_id) WHERE s.year BETWEEN 2015 AND 2019 GROUP BY m.institution_id''')
        c.execute('''CREATE TEMP TABLE base_countries AS SELECT l.institution_id,
          count(DISTINCT l.country_code) AS baseline_country_count,
          min(l.country_code) AS unique_country_candidate,
          string_agg(DISTINCT l.country_code,'|' ORDER BY l.country_code) AS baseline_country_set
          FROM studies s JOIN links l USING(study_id) WHERE s.year BETWEEN 2015 AND 2019 GROUP BY l.institution_id''')
        base = c.execute('''SELECT b.*,coalesce(k.baseline_country_count,0) AS baseline_country_count,
          CASE WHEN k.baseline_country_count=1 THEN k.unique_country_candidate ELSE NULL END AS country,
          k.baseline_country_set FROM base_counts b LEFT JOIN base_countries k USING(institution_id)
          ORDER BY institution_id''').df()
        require(not base.institution_id.duplicated().any(), 'Duplicate baseline institution')
        base['group'] = pd.Series(pd.NA, index=base.index, dtype='string')
        base['group_eligible'] = False
        country_rows = []
        for country, x in base[base.country.notna()].groupby('country', sort=True):
            groups, cuts, valid = tertiles(x.V_i)
            base.loc[x.index, 'group'] = np.array(GROUPS)[groups]
            base.loc[x.index, 'group_eligible'] = valid
            counts = np.bincount(groups, minlength=3)
            country_rows.append(dict(country=country, baseline_institutions=len(x), cut_LM=cuts[0], cut_MH=cuts[1],
                N_L=counts[0], N_M=counts[1], N_H=counts[2], structural_groups_valid=valid,
                eligible_10=valid and counts.min()>=10, eligible_20=valid and counts.min()>=20,
                eligible_30=valid and counts.min()>=30,
                tie_policy='equal integer output stays together; cuts type7; boundary ties lower'))
        country = pd.DataFrame(country_rows)
        volume = c.execute('''SELECT k.country_code AS country,count(DISTINCT s.study_id)::BIGINT AS baseline_country_studies,
          sum(1.0/s.n_countries) AS baseline_country_fractional_credit
          FROM studies s JOIN countries k USING(study_id) WHERE year BETWEEN 2015 AND 2019 GROUP BY k.country_code''').df()
        country = country.merge(volume, on='country', validate='one_to_one')
        main = country[country.eligible_20]
        require(len(main)>=3, 'Too few baseline-only qualified countries')
        _, context_cuts, valid = tertiles(main.baseline_country_studies)
        require(valid, 'National baseline tertiles unavailable')
        _, fractional_cuts, valid = tertiles(main.baseline_country_fractional_credit)
        require(valid, 'Fractional national baseline sensitivity tertiles unavailable')
        country['context'] = np.array(['Low','Middle','High'])[np.searchsorted(context_cuts, country.baseline_country_studies, side='left')]
        country['fractional_context'] = np.array(['Low','Middle','High'])[np.searchsorted(fractional_cuts, country.baseline_country_fractional_credit, side='left')]
        country['context_cut_1'] = context_cuts[0]; country['context_cut_2'] = context_cuts[1]
        country['main_country_weight'] = np.where(country.eligible_20,1/len(main),0)
        for g in GROUPS:
            country[f'ties_at_{g}'] = [int((base.loc[base.country.eq(row.country),'V_i']==getattr(row,'cut_LM' if g=='L' else 'cut_MH')).sum()) for row in country.itertuples()]
        base = base.merge(country[['country','cut_LM','cut_MH','context','fractional_context','eligible_10','eligible_20','eligible_30']], on='country', how='left', validate='many_to_one')
        for col in ['eligible_10','eligible_20','eligible_30']: base[col] = base[col].fillna(False).astype(bool)
        base['qualification'] = np.select([base.country.isna(),~base.group_eligible,~base.eligible_20],
            ['fixed_country_unknown_or_multiple','collapsed_or_empty_tertiles','group_below_N20'], default='main_eligible')
        save(out,'baseline_groups',base)
        save(out,'country_context',country)
        save(out,'country_retention',country.groupby(['context','eligible_10','eligible_20','eligible_30'],dropna=False).size().rename('countries').reset_index())
        c.register('base',base)
        cp(c, '''SELECT m.study_id,m.institution_id,b.country AS fixed_country_id,b.qualification,
          b.V_i,b."group",b.context,b.eligible_20
          FROM memberships m LEFT JOIN base b USING(institution_id)''', 'study_institution')
        cp(c, 'SELECT * FROM countries', 'study_countries')
        # No label, field, institution eligibility or AF event selection changes the baseline universe.
        # Known country sets and attributable institution identity are needed for the conditional pool.
        c.execute('''CREATE TEMP TABLE pool AS SELECT * FROM studies WHERE year BETWEEN 2020 AND 2025
          AND z>=0 AND n_institutions>0 AND n_countries>0''')
        cp(c, '''SELECT *,CASE WHEN n_institutions=1 THEN '1' WHEN n_institutions<=4 THEN '2-4' ELSE '5+' END AS team_bin
          FROM pool''', 'opportunity_studies')
        cp(c, '''SELECT m.study_id,m.institution_id FROM memberships m JOIN pool p USING(study_id)
          ''', 'opportunity_memberships')
        flow('02_baseline_2015_2019','study',c.execute('SELECT count(*) FROM studies WHERE year BETWEEN 2015 AND 2019').fetchone()[0], 'All frozen eligible study labels count toward general publication base')
        flow('03_baseline_institutions','institution',len(base),'Unique integer-study baseline >=1')
        flow('04_unique_fixed_country','institution',base.country.notna().sum(),'Only unique known baseline country')
        flow('05_domestic_tertiles_valid','country',country.structural_groups_valid.sum(),'No split of equal output; empty/collapsed groups excluded')
        flow('06_main_N20_countries','country',country.eligible_20.sum(),'At least 20 institutions in each domestic tertile')
        flow('07_main_N20_institutions','institution',base.eligible_20.sum(),'Fixed denominator for all years and draws')
        flow('08_main_period_all','study',c.execute('SELECT count(*) FROM studies WHERE year BETWEEN 2020 AND 2025').fetchone()[0],'2020-2025 frozen research units')
        flow('09_main_unknown_AF_label','study',c.execute('SELECT count(*) FROM studies WHERE year BETWEEN 2020 AND 2025 AND z<0').fetchone()[0],'Excluded from binary pool; not recoded non-AF')
        flow('10_binary_known_label','study',c.execute('SELECT count(*) FROM studies WHERE year BETWEEN 2020 AND 2025 AND z>=0').fetchone()[0],'Confirmed AF plus screen-negative/explicit non-adoption')
        flow('11_known_label_no_institution','study',c.execute('SELECT count(*) FROM studies WHERE year BETWEEN 2020 AND 2025 AND z>=0 AND n_institutions=0').fetchone()[0],'Excluded from opportunity pool')
        flow('12_known_label_inst_no_country','study',c.execute('SELECT count(*) FROM studies WHERE year BETWEEN 2020 AND 2025 AND z>=0 AND n_institutions>0 AND n_countries=0').fetchone()[0],'Excluded: all known countries absent')
        flow('13_opportunity_pool','study',c.execute('SELECT count(*) FROM pool').fetchone()[0],'Includes institutions outside fixed baseline')
        flow('14_opportunity_AF','study',c.execute('SELECT count(*) FROM pool WHERE z=1').fetchone()[0],'Confirmed AF with coherent attribution')
        flow('15_outside_main_only_opportunities','study',c.execute('''SELECT count(*) FROM pool p WHERE NOT EXISTS
          (SELECT 1 FROM memberships m JOIN base b USING(institution_id) WHERE m.study_id=p.study_id AND b.eligible_20)''').fetchone()[0],'Retained in global permutation, not discarded')
        # Raw per-institution annual state; full denominator even where no opportunities in a year.
        state = c.execute('''SELECT b.institution_id,s.year,
          count(DISTINCT s.study_id) FILTER(WHERE s.z=1) AS AF_studies,
          count(DISTINCT s.study_id) FILTER(WHERE s.z<0) AS unknown_label_studies,
          count(DISTINCT s.study_id) AS general_studies,
          count(DISTINCT s.study_id) FILTER(WHERE s.z=1 AND s.n_countries>0) AS pool_AF_studies
          FROM studies s JOIN memberships m USING(study_id) JOIN base b USING(institution_id)
          GROUP BY b.institution_id,s.year''').df()
        save(out,'institution_year_observed',state,csv=False)
        cp(c, '''SELECT s.study_id,s.year,m.institution_id,b.country AS fixed_country,
          NOT contains(string_split(s.country_set,'|'),b.country) AS fixed_country_not_in_study_country_set
          FROM studies s JOIN memberships m USING(study_id) JOIN base b USING(institution_id)
          WHERE b.eligible_20 AND s.z=1 AND s.year BETWEEN 2020 AND 2025''', 'representative_attribution_audit')
        # Institution-level earliest confirmed year and earlier unknown evidence remain distinguishable.
        history = state.groupby('institution_id').apply(lambda x:pd.Series({
            'first_confirmed_year':x.loc[x.AF_studies.gt(0),'year'].min(),
            'earliest_unknown_label_year':x.loc[x.unknown_label_studies.gt(0),'year'].min(),
            'pre2020_confirmed':bool(((x.year<2020)&x.AF_studies.gt(0)).any())}),include_groups=False).reset_index()
        save(out,'entry_year_audit',base[['institution_id','eligible_20']].merge(history,on='institution_id',how='left',validate='one_to_one'))
        cuts = dict(context_integer=context_cuts.tolist(),context_fractional=fractional_cuts.tolist(), context_frozen_on='N20 baseline-qualified countries, no AF outcomes')
        dump(out/'provenance/grouping_freeze.json',cuts)
    save(out,'sample_flow',pd.DataFrame(audit))
    dump(out/'provenance/preparation_summary.json',dict(steps=audit,seconds=time.monotonic()-start,
        context_country_N=country[country.eligible_20].groupby('context').size().to_dict(),country_list=country.loc[country.eligible_20,'country'].tolist()))
    print(f'Prepared: baseline {len(base):,}; main institutions {base.eligible_20.sum():,}; countries {country.eligible_20.sum()}; contexts {country[country.eligible_20].groupby("context").size().to_dict()}',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,default=OUT);a=p.parse_args()
    require(not a.output_dir.exists(),'Use a new output version; no overwrite')
    inputs=pins();out=a.output_dir
    out.mkdir();(out/'tables').mkdir();(out/'provenance').mkdir();(out/'scratch').mkdir()
    dump(out/'provenance/input_pins.json',inputs);dump(out/'run_config.json',configuration())
    shutil.copy2(PLAN,out/'provenance/figure2-revision-plan-3.md')
    shutil.copy2(MODULE/'README.md',out/'provenance/implementation_plan.md')
    build(out)
    require(inputs==pins(),'Frozen sources changed during preparation')
    dump(out/'provenance/prepare_complete.json',dict(status='PASS',input_pins_unchanged=True))

if __name__=='__main__':main()
