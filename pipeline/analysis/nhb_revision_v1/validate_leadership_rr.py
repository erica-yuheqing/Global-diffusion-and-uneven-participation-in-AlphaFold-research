"""Independent source-to-credit and credit-to-RR checks; never calls RR builder."""
from __future__ import annotations

import argparse
from pathlib import Path
from common import MODULE, assert_unchanged, connect, literal, output_dir, read_json, sha256, utc, write_json
from baseline_features import fingerprint
from leadership_rr import CODE, CONFIG, GUIDE, EXPORTS, attach_sources, load_inputs, markdown, summary


def numeric_difference(con, actual, expected, keys, numeric):
    """Compare exact keys/metadata and scale-aware float values, including NULLs."""
    names = [r[0] for r in con.execute(f"DESCRIBE {actual}").fetchall()]
    if names != [r[0] for r in con.execute(f"DESCRIBE {expected}").fetchall()]:
        return 1
    conditions = ["a."+keys[0]+" IS NULL", "e."+keys[0]+" IS NULL"]
    for name in names:
        if name in keys:
            continue
        if name in numeric:
            conditions.append(f"((a.{name} IS NULL)<>(e.{name} IS NULL) OR "
              f"(a.{name} IS NOT NULL AND (NOT isfinite(a.{name}) OR "
              f"abs(a.{name}-e.{name})>1e-9*greatest(1,abs(e.{name})))))")
        else:
            conditions.append(f"a.{name} IS DISTINCT FROM e.{name}")
    join = " AND ".join(f"a.{k}=e.{k}" for k in keys)
    return int(con.execute(f"SELECT count(*) FROM {actual} a FULL OUTER JOIN {expected} e ON {join} "
                            f"WHERE {' OR '.join(conditions)}").fetchone()[0])


def expected_views(con):
    # Written separately from the production window-normalization and pivot builder.
    con.execute("""CREATE VIEW expected_membership AS
      SELECT level,cohort,study_id,work_id,publication_year,
       CASE WHEN level='institution' THEN unallocated_institution_weight ELSE 0.0 END AS unallocated_output_credit
      FROM src_leadership_study_audit
      CROSS JOIN (VALUES ('country'),('institution')) l(level)
      CROSS JOIN (VALUES ('main_2020_2025',2025),('sensitivity_2020_2024',2024)) c(cohort,end_year)
      WHERE publication_year BETWEEN 2020 AND end_year AND positions_observed_complete AND
       CASE WHEN level='country' THEN first_countries>0 AND last_countries>0 AND unknown_leader_country_rows=0
        AND unaligned_leader_countries=0 AND output_countries>0
       ELSE first_institutions>0 AND last_institutions>0 AND unaligned_leader_institution_pairs=0
        AND output_institution_country_pairs>0 END""")
    con.execute("""CREATE VIEW expected_eligible AS SELECT DISTINCT level,study_id FROM expected_membership""")
    con.execute("""CREATE VIEW expected_leader_ids AS
      SELECT DISTINCT 'country' AS level,r.study_id,r.role,r.country_code AS entity_id
       FROM src_leader_country_relations r JOIN expected_eligible e ON e.study_id=r.study_id AND e.level='country'
       WHERE r.explicit_position_pair AND r.role IN ('first','last')
      UNION ALL
      SELECT DISTINCT 'institution',r.study_id,r.role,r.institution_id
       FROM src_leader_institution_relations r JOIN expected_eligible e ON e.study_id=r.study_id AND e.level='institution'
       WHERE r.explicit_position_pair AND r.role IN ('first','last')""")
    con.execute("""CREATE VIEW expected_credits AS
      SELECT l.level,l.study_id,l.role,l.entity_id,1.0/n.n_ids AS weight
      FROM expected_leader_ids l JOIN
       (SELECT level,study_id,role,count(*) AS n_ids FROM expected_leader_ids GROUP BY 1,2,3) n USING(level,study_id,role)
      UNION ALL
      SELECT 'country',r.study_id,'output',r.country_code,sum(r.country_weight)
       FROM src_participation_country_relations r JOIN expected_eligible e ON e.study_id=r.study_id AND e.level='country'
       GROUP BY r.study_id,r.country_code
      UNION ALL
      SELECT 'institution',r.study_id,'output',r.institution_id,sum(r.institution_weight)
       FROM src_participation_institution_relations r JOIN expected_eligible e ON e.study_id=r.study_id AND e.level='institution'
       GROUP BY r.study_id,r.institution_id""")
    con.execute("""CREATE VIEW expected_strata AS
      SELECT m.*,d.dimension,CASE WHEN d.dimension='overall' THEN 'all' ELSE CAST(publication_year AS VARCHAR) END AS stratum
      FROM expected_membership m CROSS JOIN (VALUES ('overall'),('year')) d(dimension)""")
    con.execute("""CREATE VIEW expected_summary AS
      SELECT level,cohort,dimension,stratum,count(*) AS study_units,
       sum(unallocated_output_credit) AS unallocated_output_credit,
       count(*)-sum(unallocated_output_credit) AS expected_allocated_output_credit
      FROM expected_strata GROUP BY 1,2,3,4""")
    con.execute("""CREATE VIEW expected_rr AS
      WITH by_role AS (
       SELECT s.level,s.cohort,s.dimension,s.stratum,b.entity_id,b.role,
        sum(b.weight) AS credit,count(DISTINCT b.study_id) AS study_count
       FROM expected_strata s JOIN expected_credits b ON s.study_id=b.study_id AND s.level=b.level
       GROUP BY 1,2,3,4,5,6),
      entities AS (SELECT DISTINCT level,cohort,dimension,stratum,entity_id FROM by_role)
      SELECT e.level,e.cohort,e.dimension,e.stratum,e.entity_id,r.role,n.study_units AS sample_study_units,
       coalesce(o.study_count,0) AS output_study_units,coalesce(l.study_count,0) AS leadership_study_units,
       coalesce(o.credit,0.0) AS output_credit,coalesce(l.credit,0.0) AS leadership_credit,
       coalesce(o.credit,0.0)/n.study_units AS output_share,
       coalesce(l.credit,0.0)/n.study_units AS leadership_share,
       coalesce(l.credit,0.0)/nullif(o.credit,0) AS rr
      FROM entities e CROSS JOIN (VALUES ('first'),('last')) r(role)
      JOIN expected_summary n USING(level,cohort,dimension,stratum)
      LEFT JOIN by_role o ON o.level=e.level AND o.cohort=e.cohort AND o.dimension=e.dimension
       AND o.stratum=e.stratum AND o.entity_id=e.entity_id AND o.role='output'
      LEFT JOIN by_role l ON l.level=e.level AND l.cohort=e.cohort AND l.dimension=e.dimension
       AND l.stratum=e.stratum AND l.entity_id=e.entity_id AND l.role=r.role""")


def check_tables(con):
    expected_views(con)
    checks = {}
    pairs = [
      ("rr_sample_membership", "expected_membership", ["level","cohort","study_id"], ["unallocated_output_credit"]),
      ("rr_study_credits", "expected_credits", ["level","study_id","role","entity_id"], ["weight"]),
      ("rr_sample_summary", "expected_summary", ["level","cohort","dimension","stratum"],
       ["unallocated_output_credit","expected_allocated_output_credit"]),
      ("leadership_rr", "expected_rr", ["level","cohort","dimension","stratum","entity_id","role"],
       ["output_credit","leadership_credit","output_share","leadership_share","rr"])]
    for actual, expected, keys, floats in pairs:
        checks[actual+"_source_values"] = numeric_difference(con, actual, expected, keys, floats)
        checks[actual+"_duplicate_keys"] = int(con.execute(
            f"SELECT count(*) FROM (SELECT {','.join(keys)} FROM {actual} GROUP BY ALL HAVING count(*)<>1)").fetchone()[0])
    queries = {
      "credit_null_or_invalid": "SELECT count(*) FROM rr_study_credits WHERE entity_id IS NULL OR weight IS NULL OR NOT isfinite(weight) OR weight<=0 OR weight>1+1e-9 OR role NOT IN ('output','first','last')",
      "leader_credit_not_one": "SELECT count(*) FROM (SELECT level,study_id,role,sum(weight) AS w FROM rr_study_credits WHERE role<>'output' GROUP BY 1,2,3) WHERE abs(w-1)>1e-9",
      "missing_position_role": "SELECT count(*) FROM (SELECT DISTINCT level,study_id FROM rr_sample_membership) s WHERE (SELECT count(DISTINCT role) FROM rr_study_credits b WHERE b.level=s.level AND b.study_id=s.study_id AND b.role<>'output')<>2",
      "output_plus_residual_not_one": "SELECT count(*) FROM rr_sample_membership s WHERE abs(s.unallocated_output_credit+(SELECT coalesce(sum(weight),0) FROM rr_study_credits b WHERE b.level=s.level AND b.study_id=s.study_id AND b.role='output')-1)>1e-9",
      "leader_without_output_entity": "SELECT count(*) FROM rr_study_credits l WHERE role<>'output' AND NOT EXISTS(SELECT 1 FROM rr_study_credits o WHERE o.level=l.level AND o.study_id=l.study_id AND o.entity_id=l.entity_id AND o.role='output')",
      "sample_position_or_scope_error": "SELECT count(*) FROM rr_sample_membership s JOIN src_leadership_study_audit a USING(study_id) WHERE NOT a.positions_observed_complete OR a.position_status='observed_singleton_unverified' OR s.publication_year NOT BETWEEN 2020 AND 2025 OR (s.cohort='sensitivity_2020_2024' AND s.publication_year>2024) OR s.work_id IS DISTINCT FROM a.work_id",
      "negative_or_invalid_residual": "SELECT count(*) FROM rr_sample_membership WHERE unallocated_output_credit IS NULL OR NOT isfinite(unallocated_output_credit) OR unallocated_output_credit < -1e-9 OR unallocated_output_credit>1+1e-9",
      "RR_numeric_invalid": "SELECT count(*) FROM leadership_rr WHERE output_credit IS NULL OR leadership_credit IS NULL OR NOT isfinite(output_credit) OR NOT isfinite(leadership_credit) OR output_credit<0 OR leadership_credit<0 OR (rr IS NOT NULL AND (NOT isfinite(rr) OR rr<0))",
      "zero_denominator_not_NULL": "SELECT count(*) FROM leadership_rr WHERE output_credit=0 AND rr IS NOT NULL",
      "known_zero_leader_not_zero_RR": "SELECT count(*) FROM leadership_rr WHERE output_credit>0 AND leadership_credit=0 AND rr IS DISTINCT FROM 0.0",
      "role_denominators_differ": "SELECT count(*) FROM (SELECT level,cohort,dimension,stratum,entity_id FROM leadership_rr GROUP BY ALL HAVING count(*)<>2 OR count(DISTINCT role)<>2 OR count(DISTINCT sample_study_units)<>1)",
      "sensitivity_not_subset": "SELECT count(*) FROM rr_sample_membership s WHERE cohort='sensitivity_2020_2024' AND NOT EXISTS(SELECT 1 FROM rr_sample_membership m WHERE m.level=s.level AND m.study_id=s.study_id AND m.cohort='main_2020_2025')",
      "wrong_sample_denominator": "SELECT count(*) FROM leadership_rr r JOIN rr_sample_summary n USING(level,cohort,dimension,stratum) WHERE r.sample_study_units<>n.study_units OR n.study_units<=0",
    }
    checks.update({k:int(con.execute(q).fetchone()[0]) for k,q in queries.items()})
    return checks


def validate(directory, threads=2, memory_gib=4):
    import pyarrow.parquet as pq
    mp = directory / "rr_manifest.json"
    m = read_json(mp)
    if m.get("schema_version") != "nhb-leadership-rr-run-v1":
        raise ValueError("Unexpected RR artifact")
    source = output_dir(Path(m["source_directory"]), existing=True)
    review = output_dir(Path(m["coverage_review_directory"]), existing=True)
    c, inv = load_inputs(source, review)
    if m["config"] != c or [(r["path"],r["sha256"]) for r in m["inputs"]] != [(r["path"],r["sha256"]) for r in inv]:
        raise ValueError("Approved config/source/implementation differs from archived run")
    assert_unchanged(m["inputs"])
    expected_names = {n+".parquet" for n in EXPORTS} | {"rr_summary.json","rr_report_zh.md"}
    if set(m["outputs"]) != expected_names:
        raise ValueError("Output inventory differs")
    con = connect(threads, memory_gib)
    try:
        attach_sources(con, source)
        for rel, rec in {**m["outputs"], **m["snapshots"]}.items():
            p = directory / rel
            if not p.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Unsafe artifact path")
            fp = fingerprint(p)
            if fp["sha256"] != rec["sha256"] or fp["size_bytes"] != rec["size_bytes"]:
                raise ValueError("Artifact content changed")
            if rel.endswith(".parquet"):
                n = pq.ParquetFile(p).metadata.num_rows
                if n != rec["rows"] or n>c["maximum_export_rows"]:
                    raise ValueError("Export rows changed/exceeded cap")
                con.execute(f"CREATE VIEW {p.stem} AS SELECT * FROM read_parquet({literal(p)})")
        expected_snapshots = {"code_and_policy/"+n for n in CODE+(CONFIG.name,GUIDE.name)}
        if set(m["snapshots"]) != expected_snapshots:
            raise ValueError("Implementation archive inventory differs")
        for n in CODE+(CONFIG.name,GUIDE.name):
            if sha256(MODULE/n) != m["snapshots"]["code_and_policy/"+n]["sha256"]:
                raise ValueError("Current code differs from archived code")
        checks = check_tables(con)
        s = summary(con)
        checks["summary_mismatch"] = int(s != read_json(directory/"rr_summary.json"))
        checks["report_mismatch"] = int(markdown(s) != (directory/"rr_report_zh.md").read_text(encoding="utf-8"))
        assert_unchanged(inv)
        blockers = [k for k,v in checks.items() if v]
        return dict(schema_version="nhb-leadership-rr-validation-v1", created_at_utc=utc(),
            rr_manifest_sha256=sha256(mp),checks=checks,blockers=blockers,
            descriptive_rr_ready=not blockers,activity_rr_ready=False,formal_models_ready=False)
    finally:
        con.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input-dir",type=Path,default=MODULE/"leadership_rr_v1")
    p.add_argument("--threads",type=int,default=2)
    p.add_argument("--memory-gib",type=int,default=4)
    args = p.parse_args()
    directory = output_dir(args.input_dir,existing=True)
    report = validate(directory,args.threads,args.memory_gib)
    target = directory/"validation_report.json"
    if target.exists():
        old = read_json(target)
        if {k:v for k,v in old.items() if k!="created_at_utc"} != {k:v for k,v in report.items() if k!="created_at_utc"}:
            raise ValueError("Existing validation differs; not overwriting")
    else:
        write_json(target,report)
    print(f"RR checks: {len(report['checks'])}; blockers: {len(report['blockers'])}")
    print(f"Descriptive RR ready: {report['descriptive_rr_ready']}; activity/formal models ready: False")
    print(f"Validation report: {target}")
    return int(bool(report["blockers"]))


if __name__ == "__main__":
    raise SystemExit(main())
