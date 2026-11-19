"""Local descriptive activity/leadership layer. No LLM, API or source changes."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from pathlib import Path
from common import MODULE, assert_unchanged, literal, output_dir, read_json, sha256
from baseline_features import fingerprint
from action_layer_v1 import ACTIONS, EXPORTS as LAYER_EXPORTS, verify_export

CONFIG = MODULE / 'activity_patterns_config_v1.json'
GUIDE = MODULE / 'ACTIVITY_PATTERNS_v1.md'
CODE = ('activity_patterns.py', 'prepare_activity_patterns.py', 'verify_activity_patterns.py',
        'test_activity_patterns.py', 'common.py', 'baseline_features.py',
        'action_layer_v1.py', 'verify_action_conflict_review_v1.py',
        'verify_action_conflict_review_v1_1.py', 'action_review.py', 'validate_leadership_rr.py',
        'leadership_rr.py')
EXPORTS = {
    'overlay_queue_linkage': 'work_id',
    'activity_study_states': 'study_id,label_level,activity',
    'activity_coverage': 'label_level,activity,dimension,stratum',
    'activity_overlap': 'activity_a,activity_b,dimension,stratum',
    'activity_entity_profiles': 'level,activity,dimension,stratum,entity_id',
    'activity_leadership_coverage': 'level,cohort,activity,dimension,stratum',
    'activity_leadership_sample': 'level,cohort,activity,sample,study_id',
    'activity_leadership_summary': 'level,cohort,activity,sample,dimension,stratum',
    'activity_leadership_rr': 'level,cohort,activity,sample,dimension,stratum,entity_id,role',
}
KEYS = {n: v.split(',') for n, v in EXPORTS.items()}
FLOATS = {
    'activity_coverage': ['supported_share_of_scope', 'supported_share_of_determinate'],
    'activity_overlap': ['joint_supported_share_of_pair_determinate'],
    'activity_entity_profiles': ['total_output_credit', 'supported_output_credit',
        'determinate_output_credit', 'uncertain_output_credit', 'not_assessed_output_credit',
        'quarantined_output_credit', 'supported_credit_share_of_determinate'],
    'activity_leadership_sample': ['unallocated_output_credit'],
    'activity_leadership_summary': ['unallocated_output_credit', 'allocated_output_credit'],
    'activity_leadership_rr': ['unallocated_output_credit', 'output_credit', 'leadership_credit',
                              'output_share', 'leadership_share', 'rr'],
}
KNOWN = {'supported', 'not_established', 'not_listed_legacy'}
STATES = KNOWN | {'uncertain', 'not_assessed', 'quarantined'}
SOURCE_TABLES = {
    'studies': ('study', 'study_records', {'study_id', 'annual_representative_work_id', 'confirmed_af',
        'period', 'publication_year', 'work_type', 'primary_subfield_id',
        'representative_actions_status', 'representative_observed_actions'}),
    'work_map': ('study', 'work_study_map', {'work_id', 'study_id'}),
    'audit': ('leadership', 'leadership_study_audit', {'study_id', 'work_id', 'publication_year'}),
    'countries': ('leadership', 'participation_country_relations', {'study_id', 'country_code', 'country_weight'}),
    'institutions': ('leadership', 'participation_institution_relations', {'study_id', 'institution_id', 'institution_weight'}),
    'membership': ('rr', 'rr_sample_membership', {'study_id', 'work_id', 'level', 'cohort',
        'publication_year', 'unallocated_output_credit'}),
    'credits': ('rr', 'rr_study_credits', {'study_id', 'level', 'role', 'entity_id', 'weight'}),
}


def config():
    c = read_json(CONFIG)
    expected = {'schema_version': 'nhb-activity-patterns-config-v1', 'protocol_version': '1.3',
        'unit': 'approved_link_study_coherent_annual_representative', 'main_years': [2020, 2025],
        'sensitivity_years': [2020, 2024], 'legacy_action_separator': '|',
        'legacy_absence': 'not_listed_legacy_not_verified_negative',
        'overlay_join': 'representative_work_id_only_no_cross_version_union',
        'mode_positive': 'any_component_supported_and_not_quarantined',
        'mode_unknown': 'no_positive_and_any_component_uncertain_or_not_assessed',
        'multi_label': True, 'imputation': False, 'rd_groups': False, 'formal_models': False,
        'provider_requests': 0, 'leader_rule': 'existing_explicit_first_last_common_samples_and_frozen_credits',
        'activity_RR': 'same_activity_same_cohort_same_stratum_leadership_credit_over_output_credit',
        'matched_overall': 'same_mode_determinate_studies_before_positive_subset',
        'dimensions': ['period', 'year', 'subfield'],
        'modes': {'precomputed_structure_use': ['retrieved_precomputed_structure'],
            'prediction_run': ['ran_alphafold', 'ran_colabfold'],
            'method_or_tool_development': ['modified_or_extended', 'developed_downstream_tool'],
            'prediction_evaluation_or_validation': ['benchmarked_or_evaluated']},
        'supplements': {'empirical_workflow_integration': ['integrated_empirical_workflow'],
            'docking_or_screening': ['docking_or_screening']}}
    if any(c.get(k) != v for k, v in expected.items()) or not 0 < c['weight_tolerance'] <= 1e-9:
        raise ValueError('Activity rules differ from this reviewed implementation')
    return c


def local_file(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(MODULE):
        raise ValueError('Expected regular file inside this analysis module')
    return path


def load_inputs(directories):
    """Authenticate selected exports, validation links and original representative lineage."""
    import pyarrow.parquet as pq
    dirs = {k: output_dir(v, existing=True) for k, v in directories.items()}
    c = config()
    verify_export(dirs['layer'])  # Read-only complete action reconstruction; not semantic certification.
    inv, manifests = [], {}
    specs = {'study': ('prepare_manifest.json', 'nhb-study-events-run-v1', 'prepare_manifest_sha256',
                      'approved_link_study_events_ready'),
        'leadership': ('prepare_manifest.json', 'nhb-leadership-audit-run-v1', 'prepare_manifest_sha256',
                       'leadership_coverage_ready'),
        'rr': ('rr_manifest.json', 'nhb-leadership-rr-run-v1', 'rr_manifest_sha256', 'descriptive_rr_ready')}
    for role, (name, schema, digest_field, ready) in specs.items():
        mp, vp = local_file(dirs[role] / name), local_file(dirs[role] / 'validation_report.json')
        m, v = read_json(mp), read_json(vp)
        if (m.get('schema_version') != schema or v.get(digest_field) != sha256(mp) or
            v.get(ready) is not True or v.get('blockers') != [] or not v.get('checks') or any(v['checks'].values())):
            raise ValueError('Matching passed upstream validation required: ' + role)
        manifests[role] = m
        inv += [fingerprint(mp), fingerprint(vp)]
    if (Path(manifests['leadership']['study_event_directory']).resolve() != dirs['study'].resolve() or
        Path(manifests['rr']['source_directory']).resolve() != dirs['leadership'].resolve()):
        raise ValueError('Representative / leadership / RR source directories differ')
    for downstream, upstream_role in [('leadership', 'study'), ('rr', 'leadership')]:
        pins = {r['path']: r['sha256'] for r in manifests[downstream]['inputs']}
        for name in ('prepare_manifest.json', 'validation_report.json'):
            p = dirs[upstream_role] / name
            if pins.get(str(p)) != sha256(p):
                raise ValueError('Upstream manifest or validation is not pinned by downstream')
    for _, (role, name, fields) in SOURCE_TABLES.items():
        p = local_file(dirs[role] / (name + '.parquet'))
        rec, expected = fingerprint(p), manifests[role]['outputs'][p.name]
        pf = pq.ParquetFile(p)
        if (rec['sha256'] != expected['sha256'] or rec['size_bytes'] != expected['size_bytes'] or
            pf.metadata.num_rows != expected['rows'] or pf.metadata.num_rows > c['maximum_input_rows'] or
            rec['size_bytes'] > c['maximum_input_bytes'] or not fields <= set(pf.schema_arrow.names)):
            raise ValueError('Selected Parquet schema/content/count exceeds source contract: ' + name)
        inv.append(rec)
    # Archived protocol documents travel with this module; no live iCloud dependency.
    for rel, pin in manifests['study']['snapshots'].items():
        if Path(rel).suffix == '.md':
            p = local_file(dirs['study'] / rel)
            rec = fingerprint(p)
            if rec['sha256'] != pin['sha256'] or rec['size_bytes'] != pin['size_bytes']:
                raise ValueError('Archived protocol changed')
            inv.append(rec)
    for name in sorted(LAYER_EXPORTS | {'layer_manifest.json', 'layer_manifest.json.sha256'}):
        inv.append(fingerprint(local_file(dirs['layer'] / name)))
    for name in CODE + (CONFIG.name, GUIDE.name):
        inv.append(fingerprint(local_file(MODULE / name)))
    # Read-only reconstruction also authenticates its historical pins. Selected files here
    # are separately locked for this new run; we do not claim re-extraction of raw documents.
    unique = {r['path']: r for r in inv}
    inv = list(unique.values())
    assert_unchanged(inv)
    return c, inv, dirs


def parse_legacy(value):
    if value is None:
        raise ValueError('Assessed legacy action collection is NULL')
    if not isinstance(value, str):
        raise ValueError('Legacy action set must be the frozen pipe-delimited string')
    items = [t.strip() for t in value.split('|')] if value.strip() else []
    if any(not t or t not in ACTIONS for t in items) or len(items) != len(set(items)):
        raise ValueError('Unknown, duplicate or empty legacy action token')
    return set(items)


def action_states(status, value, overlay):
    """Legacy unlisted labels are NOT upgraded to explicitly verified negatives."""
    if overlay is not None:
        if status != 'disagreement_unadjudicated':
            raise ValueError('Overlay unexpectedly targets a non-queued representative')
        if overlay['assessment_status'] == 'not_assessed_no_parsed_response':
            if overlay['action_decisions']:
                raise ValueError('No-response record invents actions')
            return {a: 'not_assessed' for a in ACTIONS}, 'overlay_no_response'
        decisions = overlay['action_decisions']
        if len(decisions) != len(ACTIONS) or {d['action'] for d in decisions} != set(ACTIONS):
            raise ValueError('Overlay action membership differs')
        quarantined = overlay['input_attribution_quarantined']
        result = {}
        for d in decisions:
            if d['state'] not in {'supported', 'not_established', 'uncertain'}:
                raise ValueError('Invalid overlay state')
            if d['positive_action_count_eligible'] is not (d['state'] == 'supported' and not quarantined):
                raise ValueError('Quarantine / affirmative eligibility changed')
            result[d['action']] = 'quarantined' if quarantined else d['state']
        return result, 'overlay_model_assisted'
    if status in {'ab_exact_consensus', 'adjudicated'}:
        listed = parse_legacy(value)
        return {a: 'supported' if a in listed else 'not_listed_legacy' for a in ACTIONS}, 'legacy_' + status
    if status == 'not_assessed_insufficient_evidence':
        return {a: 'not_assessed' for a in ACTIONS}, 'legacy_not_assessed'
    raise ValueError('Queued representative missing overlay or unexpected action status')


def combine_states(states):
    if not states or not set(states) <= STATES:
        raise ValueError('Empty or invalid component states')
    if 'quarantined' in states:
        return 'quarantined'
    if 'supported' in states:
        return 'supported'
    if 'uncertain' in states:
        return 'uncertain'
    if 'not_assessed' in states:
        return 'not_assessed'
    if 'not_listed_legacy' in states:
        return 'not_listed_legacy'
    return 'not_established'


STATE_FIELDS = ['study_id', 'work_id', 'publication_year', 'work_type', 'primary_subfield_id',
                'label_level', 'activity', 'state', 'action_source', 'source_status', 'positive', 'determinate']


def state_rows(studies, overlay_rows, c):
    overlay = {r['work_id']: r for r in overlay_rows}
    if len(overlay) != len(overlay_rows):
        raise ValueError('Duplicate overlay work')
    seen_studies, seen_works, result = set(), set(), []
    for s in studies:
        sid, wid = s['study_id'], s['work_id']
        if sid in seen_studies or wid in seen_works:
            raise ValueError('Repeated representative/study')
        seen_studies.add(sid); seen_works.add(wid)
        states, origin = action_states(s['source_status'], s['legacy_actions'], overlay.get(wid))
        labels = [('action', a, states[a]) for a in ACTIONS]
        for group, mapping in [('mode', c['modes']), ('supplement', c['supplements'])]:
            labels += [(group, a, combine_states([states[x] for x in components])) for a, components in mapping.items()]
        for group, activity, state in labels:
            result.append(dict(study_id=sid, work_id=wid, publication_year=s['publication_year'],
                work_type=s['work_type'], primary_subfield_id=s['primary_subfield_id'], label_level=group,
                activity=activity, state=state, action_source=origin, source_status=s['source_status'],
                positive=state == 'supported', determinate=state in KNOWN))
    return result


def attach_sources(con, dirs):
    for alias, (role, name, _) in SOURCE_TABLES.items():
        con.execute(f'CREATE VIEW src_{alias} AS SELECT * FROM read_parquet({literal(dirs[role]/(name+".parquet"))})')


def register_states(con, rows):
    import pyarrow as pa
    schema = pa.schema([(name, pa.int64() if name == 'publication_year' else
                        pa.bool_() if name in ('positive', 'determinate') else pa.string()) for name in STATE_FIELDS])
    con.register('state_arrow', pa.Table.from_pylist(rows, schema=schema))
    con.execute('CREATE TABLE activity_study_states AS SELECT * FROM state_arrow')


def install_basis(con, dirs, c):
    from action_layer_v1 import base
    overlays = base.read_rows(dirs['layer'] / 'action_layer3755.jsonl', 3755)
    con.execute("""CREATE TEMP TABLE af_studies AS SELECT study_id,annual_representative_work_id AS work_id,
      publication_year,work_type,primary_subfield_id,representative_actions_status AS source_status,
      representative_observed_actions AS legacy_actions FROM src_studies
      WHERE confirmed_af AND period='main' AND publication_year BETWEEN 2020 AND 2025""")
    names = [r[0] for r in con.execute('DESCRIBE af_studies').fetchall()]
    studies = [dict(zip(names, r)) for r in con.execute('SELECT * FROM af_studies ORDER BY study_id').fetchall()]
    if len(studies) > 100000:
        raise ValueError('Bounded confirmed-AF preparation exceeded; no truncation')
    register_states(con, state_rows(studies, overlays, c))
    import pyarrow as pa
    schema = pa.schema([('work_id', pa.string()), ('assessment_status', pa.string())])
    con.register('queue_arrow', pa.Table.from_pylist([
        {k: r[k] for k in ('work_id', 'assessment_status')} for r in overlays], schema=schema))
    con.execute("""CREATE TABLE overlay_queue_linkage AS SELECT q.*,m.study_id,
      s.annual_representative_work_id AS selected_work_id,
      coalesce(a.work_id=q.work_id,false) AS selected_in_confirmed_AF_main
      FROM queue_arrow q LEFT JOIN src_work_map m USING(work_id)
      LEFT JOIN src_studies s USING(study_id) LEFT JOIN af_studies a ON a.study_id=m.study_id""")


def stratum_sql(table):
    return f"""SELECT *, 'year' AS dimension,CAST(publication_year AS VARCHAR) AS stratum FROM {table}
      UNION ALL SELECT *, 'period','main_2020_2025' FROM {table}
      UNION ALL SELECT *, 'period','sensitivity_2020_2024' FROM {table} WHERE publication_year<=2024
      UNION ALL SELECT *, 'subfield',coalesce(primary_subfield_id,'__unknown_subfield__') FROM {table}"""


def build_descriptives(con):
    con.execute('CREATE TEMP VIEW activity_strata AS ' + stratum_sql('activity_study_states'))
    con.execute("""CREATE TABLE activity_coverage AS SELECT label_level,activity,dimension,stratum,
      count(*) AS scope_study_units,count(*) FILTER(WHERE positive) AS supported_study_units,
      count(*) FILTER(WHERE determinate) AS determinate_study_units,
      count(*) FILTER(WHERE state='not_established') AS not_established_study_units,
      count(*) FILTER(WHERE state='not_listed_legacy') AS unlisted_legacy_study_units,
      count(*) FILTER(WHERE state='uncertain') AS uncertain_study_units,
      count(*) FILTER(WHERE state='not_assessed') AS not_assessed_study_units,
      count(*) FILTER(WHERE state='quarantined') AS quarantined_study_units,
      count(*) FILTER(WHERE action_source LIKE 'legacy_%') AS legacy_source_study_units,
      count(*) FILTER(WHERE action_source LIKE 'overlay_%') AS overlay_source_study_units,
      count(*) FILTER(WHERE positive)*1.0/count(*) AS supported_share_of_scope,
      count(*) FILTER(WHERE positive)*1.0/nullif(count(*) FILTER(WHERE determinate),0) AS supported_share_of_determinate
      FROM activity_strata GROUP BY ALL""")
    con.execute("""CREATE TABLE activity_overlap AS SELECT a.activity AS activity_a,b.activity AS activity_b,
      a.dimension,a.stratum,count(*) AS scope_study_units,
      count(*) FILTER(WHERE a.determinate AND b.determinate) AS pair_determinate_study_units,
      count(*) FILTER(WHERE a.positive AND b.positive) AS joint_supported_study_units,
      count(*) FILTER(WHERE a.positive AND b.positive)*1.0/
        nullif(count(*) FILTER(WHERE a.determinate AND b.determinate),0) AS joint_supported_share_of_pair_determinate
      FROM activity_strata a JOIN activity_strata b ON a.study_id=b.study_id AND a.dimension=b.dimension
        AND a.stratum=b.stratum AND a.activity<b.activity AND a.label_level='mode' AND b.label_level='mode'
      GROUP BY ALL""")
    con.execute("""CREATE TEMP TABLE participant_basis AS
      SELECT 'country' AS level,study_id,country_code AS entity_id,sum(country_weight) AS weight
        FROM src_countries GROUP BY 1,2,3
      UNION ALL SELECT 'institution',study_id,institution_id,sum(institution_weight)
        FROM src_institutions GROUP BY 1,2,3""")
    con.execute("""CREATE TABLE activity_entity_profiles AS SELECT p.level,a.activity,a.dimension,a.stratum,p.entity_id,
      count(*) AS participation_study_units,count(*) FILTER(WHERE a.positive) AS supported_study_units,
      count(*) FILTER(WHERE a.determinate) AS determinate_study_units,
      count(*) FILTER(WHERE a.state='uncertain') AS uncertain_study_units,
      count(*) FILTER(WHERE a.state='not_assessed') AS not_assessed_study_units,
      count(*) FILTER(WHERE a.state='quarantined') AS quarantined_study_units,
      sum(p.weight) AS total_output_credit,
      sum(CASE WHEN a.positive THEN p.weight ELSE 0 END) AS supported_output_credit,
      sum(CASE WHEN a.determinate THEN p.weight ELSE 0 END) AS determinate_output_credit,
      sum(CASE WHEN a.state='uncertain' THEN p.weight ELSE 0 END) AS uncertain_output_credit,
      sum(CASE WHEN a.state='not_assessed' THEN p.weight ELSE 0 END) AS not_assessed_output_credit,
      sum(CASE WHEN a.state='quarantined' THEN p.weight ELSE 0 END) AS quarantined_output_credit,
      sum(CASE WHEN a.positive THEN p.weight ELSE 0 END)/
        nullif(sum(CASE WHEN a.determinate THEN p.weight ELSE 0 END),0) AS supported_credit_share_of_determinate
      FROM activity_strata a JOIN participant_basis p USING(study_id)
      WHERE a.label_level IN ('mode','supplement') GROUP BY ALL""")


def build_leadership(con):
    con.execute("""CREATE TEMP VIEW leadership_activity_basis AS SELECT m.*,s.primary_subfield_id,a.activity,
      a.state,a.positive,a.determinate FROM src_membership m JOIN af_studies s USING(study_id,work_id)
      JOIN activity_study_states a ON a.study_id=m.study_id AND a.label_level IN ('mode','supplement')""")
    con.execute('CREATE TEMP VIEW leadership_activity_strata AS ' + stratum_sql('leadership_activity_basis'))
    con.execute("""CREATE TABLE activity_leadership_coverage AS SELECT level,cohort,activity,dimension,stratum,
      count(*) AS common_leadership_study_units,count(*) FILTER(WHERE positive) AS supported_study_units,
      count(*) FILTER(WHERE determinate) AS determinate_study_units,
      count(*) FILTER(WHERE state='uncertain') AS uncertain_study_units,
      count(*) FILTER(WHERE state='not_assessed') AS not_assessed_study_units,
      count(*) FILTER(WHERE state='quarantined') AS quarantined_study_units
      FROM leadership_activity_strata GROUP BY ALL""")
    con.execute("""CREATE TABLE activity_leadership_sample AS
      SELECT level,cohort,activity,'positive_activity' AS sample,study_id,work_id,publication_year,
        primary_subfield_id,unallocated_output_credit FROM leadership_activity_basis WHERE positive
      UNION ALL SELECT level,cohort,activity,'determinate_matched_overall',study_id,work_id,publication_year,
        primary_subfield_id,unallocated_output_credit FROM leadership_activity_basis WHERE determinate""")
    con.execute('CREATE TEMP VIEW activity_leader_strata AS ' + stratum_sql('activity_leadership_sample'))
    con.execute("""CREATE TABLE activity_leadership_summary AS
      WITH universe AS (SELECT DISTINCT level,cohort,activity,dimension,stratum FROM activity_leadership_coverage)
      SELECT u.*,samples.sample,count(s.study_id) AS sample_study_units,
        coalesce(sum(s.unallocated_output_credit),0.0) AS unallocated_output_credit,
        count(s.study_id)-coalesce(sum(s.unallocated_output_credit),0.0) AS allocated_output_credit
      FROM universe u CROSS JOIN (VALUES ('positive_activity'),('determinate_matched_overall')) samples(sample)
      LEFT JOIN activity_leader_strata s USING(level,cohort,activity,dimension,stratum,sample) GROUP BY ALL""")
    # RR numerator and denominator use identical sample/stratum. No whole-corpus denominator.
    # Keep union of observed entities so a matched entity with zero positive output has NULL RR.
    con.execute("""CREATE TABLE activity_leadership_rr AS WITH mass AS (
      SELECT s.level,s.cohort,s.activity,s.sample,s.dimension,s.stratum,c.entity_id,
        sum(CASE WHEN c.role='output' THEN c.weight ELSE 0 END) AS output_credit,
        sum(CASE WHEN c.role='first' THEN c.weight ELSE 0 END) AS first_credit,
        sum(CASE WHEN c.role='last' THEN c.weight ELSE 0 END) AS last_credit
      FROM activity_leader_strata s JOIN src_credits c ON c.study_id=s.study_id AND c.level=s.level
      GROUP BY ALL), entities AS (
        SELECT DISTINCT level,cohort,activity,dimension,stratum,entity_id FROM mass)
      SELECT n.level,n.cohort,n.activity,n.sample,n.dimension,n.stratum,e.entity_id,r.role,
        n.sample_study_units,n.unallocated_output_credit,
        coalesce(m.output_credit,0.0) AS output_credit,
        coalesce(CASE WHEN r.role='first' THEN m.first_credit ELSE m.last_credit END,0.0) AS leadership_credit,
        coalesce(m.output_credit,0.0)/nullif(n.sample_study_units,0) AS output_share,
        coalesce(CASE WHEN r.role='first' THEN m.first_credit ELSE m.last_credit END,0.0)/
          nullif(n.sample_study_units,0) AS leadership_share,
        coalesce(CASE WHEN r.role='first' THEN m.first_credit ELSE m.last_credit END,0.0)/nullif(m.output_credit,0) AS rr
      FROM activity_leadership_summary n JOIN entities e USING(level,cohort,activity,dimension,stratum)
      CROSS JOIN (VALUES ('first'),('last')) r(role)
      LEFT JOIN mass m USING(level,cohort,activity,sample,dimension,stratum,entity_id)""")


def build_tables(con, dirs, c):
    install_basis(con, dirs, c)
    build_descriptives(con)
    build_leadership(con)


def check_tables(con):
    queries = {
      'scope_not_equal_leadership_audit': "SELECT count(*) FROM af_studies s FULL JOIN src_audit a USING(study_id) WHERE s.work_id IS DISTINCT FROM a.work_id OR s.publication_year IS DISTINCT FROM a.publication_year",
      'overlay_orphan_or_duplicate': "SELECT count(*) FROM (SELECT work_id,count(*) AS n,min(study_id) AS sid FROM overlay_queue_linkage GROUP BY 1) WHERE n<>1 OR sid IS NULL",
      'queue_scope_mismatch': "SELECT count(*) FROM af_studies s FULL JOIN (SELECT work_id FROM overlay_queue_linkage WHERE selected_in_confirmed_AF_main) q USING(work_id) WHERE (s.source_status='disagreement_unadjudicated') IS DISTINCT FROM (q.work_id IS NOT NULL)",
      'state_membership': "SELECT count(*) FROM (SELECT study_id,count(*) AS n FROM activity_study_states GROUP BY 1) WHERE n<>15",
      'state_scope': "SELECT count(*) FROM activity_study_states a LEFT JOIN af_studies s USING(study_id,work_id) WHERE s.study_id IS NULL OR a.publication_year IS DISTINCT FROM s.publication_year OR a.primary_subfield_id IS DISTINCT FROM s.primary_subfield_id OR a.state NOT IN ('supported','not_established','not_listed_legacy','uncertain','not_assessed','quarantined')",
      'positive_and_denominator_masks': "SELECT count(*) FROM activity_study_states WHERE positive IS DISTINCT FROM (state='supported') OR determinate IS DISTINCT FROM (state IN ('supported','not_established','not_listed_legacy'))",
      'quarantine_positive': "SELECT count(*) FROM activity_study_states WHERE work_id='W4411273906' AND (positive OR determinate OR state<>'quarantined')",
      'legacy_absence_not_upgraded': "SELECT count(*) FROM activity_study_states WHERE action_source LIKE 'legacy_%' AND state='not_established'",
      'coverage_partition': "SELECT count(*) FROM activity_coverage WHERE scope_study_units<>supported_study_units+not_established_study_units+unlisted_legacy_study_units+uncertain_study_units+not_assessed_study_units+quarantined_study_units OR determinate_study_units<>supported_study_units+not_established_study_units+unlisted_legacy_study_units OR scope_study_units<>legacy_source_study_units+overlay_source_study_units",
      'overlap_denominator': "SELECT count(*) FROM activity_overlap WHERE joint_supported_study_units>pair_determinate_study_units OR pair_determinate_study_units>scope_study_units",
      'participant_weights': "SELECT count(*) FROM participant_basis WHERE entity_id IS NULL OR weight IS NULL OR NOT isfinite(weight) OR weight<0 OR weight>1+1e-9",
      'entity_positive_denominator': "SELECT count(*) FROM activity_entity_profiles WHERE supported_study_units>determinate_study_units OR determinate_study_units>participation_study_units OR supported_output_credit>determinate_output_credit+1e-9 OR abs(total_output_credit-determinate_output_credit-uncertain_output_credit-not_assessed_output_credit-quarantined_output_credit)>1e-9*greatest(1,total_output_credit)",
      'leader_sample_scope': "SELECT count(*) FROM activity_leadership_sample s LEFT JOIN leadership_activity_basis b USING(level,cohort,activity,study_id,work_id) WHERE b.study_id IS NULL OR (s.sample='positive_activity' AND NOT b.positive) OR (s.sample='determinate_matched_overall' AND NOT b.determinate) OR s.sample NOT IN ('positive_activity','determinate_matched_overall')",
      'positive_sample_not_matched_subset': "SELECT count(*) FROM activity_leadership_sample p WHERE sample='positive_activity' AND NOT EXISTS(SELECT 1 FROM activity_leadership_sample m WHERE m.sample='determinate_matched_overall' AND m.level=p.level AND m.cohort=p.cohort AND m.activity=p.activity AND m.study_id=p.study_id)",
      'leader_weight_conservation': "SELECT count(*) FROM (SELECT level,study_id,role,sum(weight) AS w FROM src_credits WHERE role IN ('first','last') GROUP BY ALL) WHERE abs(w-1)>1e-9",
      'leader_credit_output_residual': "SELECT count(*) FROM activity_leadership_summary n LEFT JOIN (SELECT level,cohort,activity,sample,dimension,stratum,sum(output_credit) FILTER(WHERE role='first') AS o,sum(leadership_credit) FILTER(WHERE role='first') AS f,sum(leadership_credit) FILTER(WHERE role='last') AS l FROM activity_leadership_rr GROUP BY ALL) r USING(level,cohort,activity,sample,dimension,stratum) WHERE abs(coalesce(r.o,0)+n.unallocated_output_credit-n.sample_study_units)>1e-9*greatest(1,n.sample_study_units) OR abs(coalesce(r.f,0)-n.sample_study_units)>1e-9*greatest(1,n.sample_study_units) OR abs(coalesce(r.l,0)-n.sample_study_units)>1e-9*greatest(1,n.sample_study_units)",
      'RR_formula_or_nulls': "SELECT count(*) FROM activity_leadership_rr WHERE (output_credit=0 AND rr IS NOT NULL) OR (output_credit>0 AND (rr IS NULL OR NOT isfinite(rr) OR abs(rr-leadership_credit/output_credit)>1e-9*greatest(1,rr))) OR (sample_study_units=0 AND (output_share IS NOT NULL OR leadership_share IS NOT NULL)) OR output_credit<0 OR leadership_credit<0",
      'RR_denominator': "SELECT count(*) FROM activity_leadership_rr r JOIN activity_leadership_summary n USING(level,cohort,activity,sample,dimension,stratum) WHERE r.sample_study_units<>n.sample_study_units OR r.unallocated_output_credit IS DISTINCT FROM n.unallocated_output_credit",
    }
    result = {k: int(con.execute(q).fetchone()[0]) for k, q in queries.items()}
    for table, keys in KEYS.items():
        result[table + '_duplicate_keys'] = int(con.execute(
            f"SELECT count(*) FROM (SELECT {','.join(keys)},count(*) AS n FROM {table} GROUP BY ALL HAVING n<>1)").fetchone()[0])
    return result


def summary(con):
    def records(query):
        cur = con.execute(query); names = [d[0] for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]
    return {'schema_version': 'nhb-activity-patterns-summary-v1',
        'confirmed_AF_main_studies': int(con.execute('SELECT count(*) FROM af_studies').fetchone()[0]),
        'overlay_queue_works': int(con.execute('SELECT count(*) FROM overlay_queue_linkage').fetchone()[0]),
        'overlay_selected_representatives': int(con.execute('SELECT count(*) FROM overlay_queue_linkage WHERE selected_in_confirmed_AF_main').fetchone()[0]),
        'action_sources': records('SELECT action_source,count(DISTINCT study_id) AS studies FROM activity_study_states GROUP BY 1 ORDER BY 1'),
        'main_mode_coverage': records("SELECT * FROM activity_coverage WHERE label_level='mode' AND dimension='period' AND stratum='main_2020_2025' ORDER BY activity"),
        'export_rows': {n: int(con.execute('SELECT count(*) FROM ' + n).fetchone()[0]) for n in EXPORTS},
        'formal_models_ready': False, 'provider_requests': 0, 'original_final_database_modified': False,
        'independent_human_gold_standard': False, 'complete_version_deduplication_claimed': False}


def markdown(s):
    lines = ['# 活动与领导描述 v1', '',
        '确认 AF 主期研究单元：' + str(s['confirmed_AF_main_studies']), '',
        '以下是既有文本与模型辅助动作层的描述，不是因果效果或独立人工金标准。', '',
        '| 活动 | 支持 | 可判定 | 不确定 | 无判定 | 隔离 |', '|---|---:|---:|---:|---:|---:|']
    for r in s['main_mode_coverage']:
        lines.append('| ' + str(r['activity']) + ' | ' + ' | '.join(str(r[k]) for k in
            ('supported_study_units','determinate_study_units','uncertain_study_units',
             'not_assessed_study_units','quarantined_study_units')) + ' |')
    lines += ['', '可判定分母含旧最终动作集合中的未列出标签；这不是经逐动作证据核实的否定。',
        '模式允许多标签，不求和当论文总数；某合著机构参与该类研究不等于它亲自执行该行为。',
        'RR 使用同活动、同共同完整署名样本、同年/领域/期别的分子分母；首末位分开。',
        'matched_overall 为该模式可判定子样本的总体 RR，positive_activity 为其中支持该模式的子集。',
        '国家/机构缺失及嵌套未分配残差保留；零产出 RR 为 NULL。稀疏单位不排序、不作显著性判断。',
        '分类覆盖、前期基础关联、构成标准化、正式模型和引用可见度尚未完成。', '']
    return '\n'.join(lines)
