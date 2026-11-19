"""Approved descriptive RR, keeping source weights and unallocated institutional mass."""
from __future__ import annotations

from pathlib import Path
from common import MODULE, assert_unchanged, literal, output_dir, read_json, sha256
from baseline_features import fingerprint

CONFIG = MODULE / "leadership_rr_config_v1.json"
CODE = ("common.py", "baseline_features.py", "leadership_rr.py", "compute_leadership_rr.py",
        "validate_leadership_rr.py", "test_leadership_rr.py")
GUIDE = MODULE / "LEADERSHIP_RR_v1.md"
SOURCE_NAMES = ("leadership_study_audit", "leader_country_relations", "leader_institution_relations",
                "participation_country_relations", "participation_institution_relations")
REQUIRED = {
    "leadership_study_audit": {"study_id", "work_id", "publication_year", "position_status",
        "positions_observed_complete", "first_countries", "last_countries", "unknown_leader_country_rows",
        "unaligned_leader_countries", "output_countries", "first_institutions", "last_institutions",
        "unaligned_leader_institution_pairs", "output_institution_country_pairs", "common_country_candidate",
        "common_nested_institution_candidate", "unallocated_institution_weight"},
    "leader_country_relations": {"study_id", "role", "country_code", "explicit_position_pair"},
    "leader_institution_relations": {"study_id", "role", "institution_id", "explicit_position_pair"},
    "participation_country_relations": {"study_id", "country_code", "country_weight"},
    "participation_institution_relations": {"study_id", "institution_id", "institution_weight"},
}
EXPORTS = {"rr_sample_membership": "level,cohort,study_id",
           "rr_study_credits": "level,study_id,role,entity_id",
           "leadership_rr": "level,cohort,dimension,stratum,entity_id,role",
           "rr_sample_summary": "level,cohort,dimension,stratum"}


def config():
    c = read_json(CONFIG)
    expected = {"schema_version": "nhb-leadership-rr-config-v1", "status": "user_approved",
        "main_years": [2020, 2025], "sensitivity_years": [2020, 2024], "roles": ["first", "last"],
        "dimensions": ["overall", "year"], "institution_leader_weight":
        "equal_distinct_institution_IDs_of_position_author_1_over_L", "singletons_in_main": False,
        "country_leader_weight": "equal_distinct_countries_of_position_author_1_over_c",
        "country_output_weight": "existing_1_over_k", "institution_output_weight":
        "existing_nested_1_over_k_m_residual_retained", "share_denominator":
        "same_level_same_cohort_same_stratum_study_N_including_unallocated_output_credit",
        "unknown_not_zero": True, "activity_stratification": False,
        "inference": "descriptive_only_no_CI_no_p_values"}
    if any(c.get(k) != v for k,v in expected.items()) or not 0 < c["weight_tolerance"] <= 1e-9:
        raise ValueError("RR policy changed; requires separately reviewed implementation")
    return c


def load_inputs(source, review):
    import pyarrow.parquet as pq
    source, review = output_dir(source, existing=True), output_dir(review, existing=True)
    c = config()
    mp = source / "prepare_manifest.json"
    m = read_json(mp)
    v = read_json(source / "validation_report.json")
    if (m.get("schema_version") != "nhb-leadership-audit-run-v1" or
        v.get("prepare_manifest_sha256") != sha256(mp) or v.get("leadership_coverage_ready") is not True
        or v.get("blockers") != [] or not v.get("checks") or any(v["checks"].values())):
        raise ValueError("Matching passed source-to-export leadership validation required")
    inv = [fingerprint(mp), fingerprint(source / "validation_report.json")]
    # Authenticate all upstream exported and archived content, but do not re-read raw shards.
    for rel, expected in {**m["outputs"], **m["snapshots"]}.items():
        p = source / rel
        if not p.resolve().is_relative_to(source.resolve()):
            raise ValueError("Unsafe source archive path")
        rec = fingerprint(p)
        if rec["sha256"] != expected["sha256"] or rec["size_bytes"] != expected["size_bytes"]:
            raise ValueError("Leadership archive changed")
        inv.append(rec)
    for name in SOURCE_NAMES:
        p = source / (name+".parquet")
        pf = pq.ParquetFile(p)
        if not REQUIRED[name].issubset(pf.schema_arrow.names):
            raise ValueError(f"Missing RR input columns: {name}")
        if (pf.metadata.num_rows != m["outputs"][p.name]["rows"] or
            pf.metadata.num_rows > c["maximum_input_rows_per_file"] or
            p.stat().st_size > c["maximum_input_bytes_per_file"]):
            raise ValueError("Bounded input rows/bytes exceeded or changed")
    rm = read_json(review / "review_manifest.json")
    if rm.get("schema_version") != "nhb-leadership-coverage-review-run-v1":
        raise ValueError("Coverage review missing")
    inv.append(fingerprint(review / "review_manifest.json"))
    review_inputs = {str(Path(r["path"]).resolve()): r["sha256"] for r in rm["inputs"]}
    for r in inv[:-1]:
        if review_inputs.get(str(Path(r["path"]).resolve())) != r["sha256"]:
            raise ValueError("Coverage review does not authenticate this leadership archive")
    for rel, digest in rm["outputs"].items():
        p = review / rel
        if not p.resolve().is_relative_to(review.resolve()):
            raise ValueError("Unsafe review archive path")
        rec = fingerprint(p)
        if rec["sha256"] != digest:
            raise ValueError("Coverage review changed")
        inv.append(rec)
    reviewed = read_json(review / "coverage_review.json")
    totals = read_json(source / "coverage_summary.json")["totals"]
    overall = next(r for r in reviewed["coverage"] if r["dimension"] == "overall")
    if (overall["study_units"] != totals["confirmed_AF_main_study_units"] or
        overall["country_common_units"] != totals["common_country_units"] or
        overall["institution_common_units"] != totals["common_nested_institution_units"]):
        raise ValueError("Reviewed sample counts differ")
    inv += [fingerprint(MODULE / n) for n in CODE] + [fingerprint(CONFIG), fingerprint(GUIDE)]
    assert_unchanged(inv)
    return c, inv


def attach_sources(con, source):
    for name in SOURCE_NAMES:
        con.execute(f"CREATE VIEW src_{name} AS SELECT * FROM read_parquet({literal(source/(name+'.parquet'))})")


MEMBERSHIP_SQL = """
SELECT level,cohort,study_id,work_id,publication_year,
 CASE WHEN level='institution' THEN unallocated_institution_weight ELSE 0.0 END AS unallocated_output_credit
FROM src_leadership_study_audit
CROSS JOIN (VALUES ('country'),('institution')) l(level)
CROSS JOIN (VALUES ('main_2020_2025',2025),('sensitivity_2020_2024',2024)) c(cohort,end_year)
WHERE publication_year BETWEEN 2020 AND end_year AND
 CASE WHEN level='country' THEN common_country_candidate ELSE common_nested_institution_candidate END
"""

CREDITS_SQL = """
WITH eligible AS (SELECT DISTINCT level,study_id FROM rr_sample_membership),
 country_leaders AS (
  SELECT DISTINCT 'country' AS level,r.study_id,r.role,r.country_code AS entity_id
  FROM src_leader_country_relations r JOIN eligible e ON e.study_id=r.study_id AND e.level='country'
  WHERE r.explicit_position_pair AND r.role IN ('first','last')),
 institution_leaders AS (
  SELECT DISTINCT 'institution' AS level,r.study_id,r.role,r.institution_id AS entity_id
  FROM src_leader_institution_relations r JOIN eligible e ON e.study_id=r.study_id AND e.level='institution'
  WHERE r.explicit_position_pair AND r.role IN ('first','last')),
 leader_ids AS (SELECT * FROM country_leaders UNION ALL SELECT * FROM institution_leaders)
SELECT level,study_id,role,entity_id,
 1.0/count(*) OVER (PARTITION BY level,study_id,role) AS weight FROM leader_ids
UNION ALL
SELECT 'country',r.study_id,'output',r.country_code,sum(r.country_weight)
 FROM src_participation_country_relations r JOIN eligible e ON e.study_id=r.study_id AND e.level='country'
 GROUP BY r.study_id,r.country_code
UNION ALL
SELECT 'institution',r.study_id,'output',r.institution_id,sum(r.institution_weight)
 FROM src_participation_institution_relations r JOIN eligible e ON e.study_id=r.study_id AND e.level='institution'
 GROUP BY r.study_id,r.institution_id
"""


def stratum_view(con):
    con.execute("""CREATE VIEW sample_strata AS
      SELECT *, 'overall' AS dimension,'all' AS stratum FROM rr_sample_membership
      UNION ALL SELECT *, 'year',CAST(publication_year AS VARCHAR) FROM rr_sample_membership""")


def build_tables(con):
    con.execute("CREATE TABLE rr_sample_membership AS " + MEMBERSHIP_SQL)
    con.execute("CREATE TABLE rr_study_credits AS " + CREDITS_SQL)
    stratum_view(con)
    con.execute("""CREATE TABLE rr_sample_summary AS
      SELECT level,cohort,dimension,stratum,count(*) AS study_units,
       sum(unallocated_output_credit) AS unallocated_output_credit,
       count(*)-sum(unallocated_output_credit) AS expected_allocated_output_credit
      FROM sample_strata GROUP BY level,cohort,dimension,stratum""")
    con.execute("""CREATE TABLE leadership_rr AS
      WITH agg AS (
       SELECT s.level,s.cohort,s.dimension,s.stratum,b.entity_id,
        sum(CASE WHEN b.role='output' THEN b.weight ELSE 0 END) AS output_credit,
        sum(CASE WHEN b.role='first' THEN b.weight ELSE 0 END) AS first_credit,
        sum(CASE WHEN b.role='last' THEN b.weight ELSE 0 END) AS last_credit,
        count(DISTINCT CASE WHEN b.role='output' THEN s.study_id END) AS output_study_units,
        count(DISTINCT CASE WHEN b.role='first' THEN s.study_id END) AS first_study_units,
        count(DISTINCT CASE WHEN b.role='last' THEN s.study_id END) AS last_study_units
       FROM sample_strata s JOIN rr_study_credits b ON s.level=b.level AND s.study_id=b.study_id
       GROUP BY s.level,s.cohort,s.dimension,s.stratum,b.entity_id)
      SELECT a.level,a.cohort,a.dimension,a.stratum,a.entity_id,role,n.study_units AS sample_study_units,
       output_study_units,CASE WHEN role='first' THEN first_study_units ELSE last_study_units END AS leadership_study_units,
       output_credit,CASE WHEN role='first' THEN first_credit ELSE last_credit END AS leadership_credit,
       output_credit/n.study_units AS output_share,
       (CASE WHEN role='first' THEN first_credit ELSE last_credit END)/n.study_units AS leadership_share,
       (CASE WHEN role='first' THEN first_credit ELSE last_credit END)/nullif(output_credit,0) AS rr
      FROM agg a JOIN rr_sample_summary n USING(level,cohort,dimension,stratum)
      CROSS JOIN (VALUES ('first'),('last')) r(role)""")


def summary(con):
    records = con.execute("SELECT * FROM rr_sample_summary WHERE dimension='overall' ORDER BY level,cohort").fetchall()
    keys = [d[0] for d in con.description]
    return dict(schema_version="nhb-leadership-rr-summary-v1", samples=[dict(zip(keys,r)) for r in records],
        rr_computed=True, inference="descriptive_only", confidence_intervals_computed=False,
        formal_models_ready=False, activity_rr_ready=False, complete_version_deduplication_claimed=False,
        institutional_residual_renormalized=False, rr_is_adoption_risk_ratio=False)


def markdown(s):
    lines = ["# 首末作者领导代表性RR：描述结果", "",
      "RR=位置领导份额/AF产出份额；不是采用风险比或因果效应。首末位置为代理归属。", "",
      "| 层级 | 样本 | 研究数N | 机构未分配产出信用 |", "|---|---|---:|---:|"]
    for r in s["samples"]:
        lines.append(f'| {r["level"]} | {r["cohort"]} | {r["study_units"]:,} | {r["unallocated_output_credit"]:.6f} |')
    return "\n".join(lines + ["", "完整实体结果在leadership_rr.parquet，信用权重在rr_study_credits.parquet。",
      "首末作者各位置单位信用守恒；机构产出残余保留，份额分母始终为相同样本N。",
      "没有置信区间、p值、活动分层或任一领导合并；不将小样本RR用于精确排名。",
      "2025覆盖下降，须同时参照2020–2024敏感性；完整案例不能保证无选择偏差。", ""])
