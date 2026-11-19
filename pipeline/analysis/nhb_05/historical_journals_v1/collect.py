"""Bounded, credential-free source enrichment for the frozen Figure 5 inputs.

This collector never calls LLM endpoints or substitutes present-day journal
metrics for historical ones. Archives are append-only; derived snapshots use
new version directories. Source metadata are observed at retrieval time.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import duckdb
import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "visibility_venues_v2/out_v3"
STORE = HERE / "collection_v1"
FIELDS = "id,display_name,issn_l,issn,type"
TYPES = {"journal", "repository", "conference", "ebook platform", "book series", "other", "metadata"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(data)


def dump_new(path, data):
    write_new(path, (json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode())


def sid(value):
    require(isinstance(value, str), "Non-string source ID")
    short = re.sub(r"^https://openalex\.org/", "", value)
    require(re.fullmatch(r"S[0-9]+", short) is not None, "Invalid source ID")
    return short


def issn(value):
    if value is None:
        return None
    require(isinstance(value, str), "Invalid ISSN type")
    s = re.sub(r"[\s-]", "", value).upper()
    if not re.fullmatch(r"[0-9]{7}[0-9X]", s):
        return None
    check = 10 if s[-1] == "X" else int(s[-1])
    if (sum(int(s[i]) * (8 - i) for i in range(7)) + check) % 11:
        return None
    return s[:4] + "-" + s[4:]


def lit(path):
    return "'" + str(path).replace("'", "''") + "'"


def prepare_scope(source=SOURCE, store=STORE):
    source, store = Path(source), Path(store)
    manifest_path = source / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    names = ["data/studies.parquet", "data/sources.parquet", "data/source_paired_outcomes.parquet",
             "data/institution_source_baseline.parquet"]
    names += [f"data/source_references/year_{y}.parquet" for y in range(2020, 2026)]
    pins = {}
    for name in names:
        path = source / name
        digest = sha(path)
        require(digest == manifest["outputs"][name]["sha256"], "Upstream bytes differ: " + name)
        pins[name] = {"sha256": digest, "bytes": path.stat().st_size}
    signature = {"source_directory": str(source.resolve()), "manifest_sha256": sha(manifest_path), "inputs": pins}
    if (store / "scope_manifest.json").exists():
        old = json.loads((store / "scope_manifest.json").read_text())
        require(old["upstream"] == signature, "Scope input signature differs")
        for name, pin in old["outputs"].items():
            require(sha(store / name) == pin["sha256"], "Scope output differs")
        return pd.read_parquet(store / "source_scope.parquet")
    c = duckdb.connect()
    c.execute("SET threads=2")
    c.execute("SET memory_limit='2GiB'")
    c.execute("SET preserve_insertion_order=false")
    c.execute(f"CREATE VIEW paired AS SELECT * FROM read_parquet({lit(source/'data/source_paired_outcomes.parquet')})")
    c.execute("CREATE TEMP TABLE keys AS SELECT DISTINCT institution_id, year, work_type, subfield FROM paired WHERE primary_supported")
    c.execute(f"CREATE VIEW references_all AS SELECT * FROM read_parquet({lit(source/'data/source_references/*.parquet')})")
    c.execute("CREATE TEMP TABLE reference_sources AS SELECT DISTINCT r.source_id FROM references_all r JOIN keys k USING(institution_id,year,work_type,subfield) WHERE r.source_id IS NOT NULL")
    c.execute(f"CREATE VIEW studies AS SELECT * FROM read_parquet({lit(source/'data/studies.parquet')})")
    c.execute("CREATE TEMP TABLE af_sources AS SELECT source_id, count(*) AS af_studies FROM studies WHERE confirmed_af AND year BETWEEN 2020 AND 2025 AND source_id IS NOT NULL GROUP BY source_id")
    c.execute(f"CREATE TEMP TABLE baseline_sources AS SELECT DISTINCT b.source_id FROM read_parquet({lit(source/'data/institution_source_baseline.parquet')}) b JOIN (SELECT DISTINCT institution_id FROM keys) i USING(institution_id)")
    c.execute(f"CREATE VIEW source_registry AS SELECT * FROM read_parquet({lit(source/'data/sources.parquet')})")
    scope = c.execute("""WITH union_ids AS (
        SELECT source_id FROM af_sources UNION SELECT source_id FROM reference_sources UNION SELECT source_id FROM baseline_sources)
        SELECT u.source_id, s.source_name AS local_name, coalesce(a.af_studies,0) AS af_studies,
          a.source_id IS NOT NULL AS af_source, r.source_id IS NOT NULL AS matched_reference_source,
          b.source_id IS NOT NULL AS baseline_source, s.studies AS local_studies
        FROM union_ids u LEFT JOIN source_registry s USING(source_id)
        LEFT JOIN af_sources a USING(source_id) LEFT JOIN reference_sources r USING(source_id)
        LEFT JOIN baseline_sources b USING(source_id)
        ORDER BY af_source DESC, af_studies DESC, local_studies DESC, source_id""").fetchdf()
    require(scope.source_id.is_unique and not scope.source_id.isna().any(), "Duplicate/missing scope IDs")
    for value in scope.source_id:
        sid(value)
    store.mkdir(parents=True, exist_ok=True)
    scope.to_parquet(store / "source_scope.parquet", index=False)
    scope.to_csv(store / "source_scope.csv", index=False)
    summary = {"target_sources": len(scope), "af_sources": int(scope.af_source.sum()),
               "reference_sources": int(scope.matched_reference_source.sum()), "baseline_sources": int(scope.baseline_source.sum()),
               "scope_note": "All known AF-main source IDs plus current Figure5b primary-matched reference and participating-institution baseline source IDs; not all possible future rank-model targets.",
               "historical_years": list(range(2015, 2026)), "cartesian_source_year_upper_bound": len(scope) * 11}
    dump_new(store / "scope_manifest.json", {"schema": "historical_journal_acquisition_scope_v1", "created_utc": now(),
            "upstream": signature, "summary": summary,
            "outputs": {n: {"sha256": sha(store/n), "bytes": (store/n).stat().st_size} for n in ["source_scope.parquet", "source_scope.csv"]}})
    c.close()
    return scope


def metadata_url(ids):
    require(1 <= len(ids) <= 100 and len(set(ids)) == len(ids), "Batch must contain 1–100 unique IDs")
    ids = [sid(x) for x in ids]
    return "https://api.openalex.org/sources?" + urllib.parse.urlencode({"filter": "ids.openalex:" + "|".join(ids),
                                                                     "select": FIELDS, "per_page": 100})


def parse_metadata(body, requested):
    require(not body.lstrip().startswith(b"<"), "HTML is not metadata")
    data = json.loads(body)
    require(isinstance(data, dict) and isinstance(data.get("results"), list), "Unexpected API envelope")
    rows, seen = [], set()
    require(data.get("meta", {}).get("count", len(data["results"])) <= len(requested), "Unexpected result count/pagination")
    for row in data["results"]:
        identifier = sid(row["id"])
        require(identifier in requested and identifier not in seen, "Unrequested/duplicate response ID")
        seen.add(identifier)
        require(row.get("type") in TYPES, "Unknown source type; preserve archive, review schema")
        require(isinstance(row.get("display_name"), str), "Missing source name")
        raw_list = row.get("issn")
        require(raw_list is None or (isinstance(raw_list, list) and all(isinstance(v,str) for v in raw_list)), "Malformed ISSN list")
        raw_values = [v for v in [row.get("issn_l")] + (raw_list or []) if v]
        valid = sorted({issn(v) for v in raw_values if issn(v)})
        invalid = sorted({v for v in raw_values if not issn(v)})
        rows.append({"source_id": identifier, "api_name": row["display_name"], "source_type": row["type"],
                     "issn_l": issn(row.get("issn_l")), "issns_json": json.dumps(valid),
                     "invalid_issns_json": json.dumps(invalid), "raw_issn_l": row.get("issn_l"),
                     "metadata_status": "resolved" if valid else "resolved_without_valid_issn"})
    return rows, sorted(set(requested) - seen), data.get("meta", {}).get("cost_usd")


class AllowedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(urllib.parse.urlparse(newurl).hostname == urllib.parse.urlparse(req.full_url).hostname,
                "Cross-host redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Collector:
    def __init__(self, store, max_requests=400, interval=.75, timeout=30):
        self.store, self.cap, self.interval, self.timeout = Path(store), max_requests, interval, timeout
        self.lock, self.stop = threading.Lock(), threading.Event()
        self.sent, self.next_send = 0, 0.0

    def fetch(self, ids):
        url = metadata_url(ids)
        for attempt in range(2):
            with self.lock:
                if self.stop.is_set() or self.sent >= self.cap:
                    return False
                time.sleep(max(0, self.next_send - time.monotonic()))
                self.next_send = time.monotonic() + self.interval
                self.sent += 1
            stamp = uuid.uuid4().hex
            record = {"schema": "source_http_attempt_v1", "request_id": stamp, "requested_ids": ids,
                      "url": url, "started_utc": now(), "credential_mode": "anonymous_no_keys_read", "attempt": attempt+1}
            body = b""
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AlphaFoldResearch-journal-enrichment/1.0", "Accept": "application/json"})
                with urllib.request.build_opener(AllowedRedirect()).open(req, timeout=self.timeout) as response:
                    record.update(http_status=response.status, content_type=response.headers.get("Content-Type"),
                                  rate_remaining=response.headers.get("X-RateLimit-Remaining"),
                                  credits_used=response.headers.get("X-RateLimit-Credits-Used"))
                    body = response.read(4*1024*1024+1)
                    require(len(body) <= 4*1024*1024, "Response size cap exceeded")
                rows, absent, cost = parse_metadata(body, ids)
                record.update(status="validated", returned_ids=[r["source_id"] for r in rows], absent_ids=absent,
                              provider_meta_cost_usd=cost,
                              cost_note="Server-reported API accounting value, not a demonstrated monetary charge; no credential or paid plan used.")
                remaining = record.get("rate_remaining")
                if remaining is not None and float(remaining) <= 5:
                    self.stop.set()
            except urllib.error.HTTPError as error:
                body = error.read(65536)
                record.update(http_status=error.code, status="http_error", error_type="HTTPError")
                if error.code in (401,403,429):
                    self.stop.set()
            except Exception as error:
                record.update(status="failed", error_type=type(error).__name__)
            record["finished_utc"] = now()
            if body:
                raw = self.store / "raw/openalex" / (stamp + ".body")
                write_new(raw, body)
                record.update(raw_file=str(raw.relative_to(self.store)), raw_sha256=sha(raw), raw_bytes=len(body))
            dump_new(self.store / "requests" / (stamp + ".json"), record)
            if record["status"] == "validated":
                return True
            if self.stop.is_set() or record.get("http_status",0) not in (0,500,502,503,504):
                return False
        return False


def archives(store):
    rows, attempted = {}, set()
    for path in sorted((Path(store)/"requests").glob("*.json")):
        record = json.loads(path.read_text())
        if record["status"] != "validated":
            continue
        raw = Path(store) / record["raw_file"]
        require(sha(raw) == record["raw_sha256"], "Raw archive hash differs")
        parsed, absent, _ = parse_metadata(raw.read_bytes(), record["requested_ids"])
        attempted.update(record["requested_ids"])
        for row in parsed:
            require(row["source_id"] not in rows, "Duplicate successful source archive")
            row.update(observed_utc=record["finished_utc"], raw_file=record["raw_file"], raw_sha256=record["raw_sha256"])
            rows[row["source_id"]] = row
    return rows, attempted


def fetch_metadata(scope, store, limit=None, workers=3, max_requests=400, interval=.75, timeout=30):
    existing, attempted = archives(store)
    require(attempted.issubset(set(scope.source_id)), "Archive outside frozen scope")
    pending = [v for v in scope.source_id if v not in attempted]
    if limit is not None:
        pending = pending[:limit]
    batches = [pending[i:i+100] for i in range(0,len(pending),100)]
    print(f"Sources: {len(scope):,}; archived resolved: {len(existing):,}; selected pending: {len(pending):,}; batches: {len(batches)}", flush=True)
    collector = Collector(store,max_requests,interval,timeout)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(collector.fetch, ids) for ids in batches]
        for i, future in enumerate(as_completed(futures),1):
            future.result()
            if i % 10 == 0 or i == len(batches):
                print(f"Batch tasks processed: {i}/{len(batches)}; HTTP sends: {collector.sent}; rate/access stop: {collector.stop.is_set()}", flush=True)
    return collector.sent


def snapshot(scope, store):
    store = Path(store)
    rows, attempted = archives(store)
    out = store / "snapshots" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6])
    out.mkdir(parents=True)
    columns = ["source_id", "api_name", "source_type", "issn_l", "issns_json", "invalid_issns_json", "raw_issn_l", "metadata_status", "observed_utc", "raw_file", "raw_sha256"]
    metadata = pd.DataFrame(list(rows.values()),columns=columns)
    merged = scope.merge(metadata,on="source_id",how="left",validate="one_to_one")
    merged.loc[merged.metadata_status.isna(),"metadata_status"] = merged.loc[merged.metadata_status.isna(),"source_id"].map(lambda s:"not_returned_by_api" if s in attempted else "not_yet_resolved")
    merged.to_parquet(out/"source_metadata.parquet",index=False)
    merged.to_csv(out/"source_metadata.csv",index=False)
    crosswalk = []
    for row in metadata.to_dict("records"):
        for value in json.loads(row["issns_json"]):
            crosswalk.append({"source_id":row["source_id"], "issn":value,"is_issn_l":value==row["issn_l"],"source_type":row["source_type"]})
    crosswalk = pd.DataFrame(crosswalk,columns=["source_id","issn","is_issn_l","source_type"])
    crosswalk.to_csv(out/"issn_crosswalk.csv",index=False)
    ambiguous = crosswalk.groupby("issn").source_id.nunique()
    collisions = crosswalk[crosswalk.issn.isin(ambiguous[ambiguous>1].index)]
    collisions.to_csv(out/"issn_collisions_review.csv",index=False)
    merged.loc[merged.af_source].to_csv(out/"af_sources_priority.csv",index=False)
    summary={"target_sources":len(scope), "resolved_sources":len(rows), "validated_requested_sources":len(attempted),
             "api_not_returned":len(attempted-set(rows)), "pending_sources":len(scope)-len(attempted),
             "types":{str(k):int(v) for k,v in merged.source_type.value_counts(dropna=False).items()},
             "af_types":{str(k):int(v) for k,v in merged.loc[merged.af_source,"source_type"].value_counts(dropna=False).items()},
             "valid_issn_sources":int(merged.issns_json.fillna("[]").ne("[]").sum()),
             "collision_issns":int((ambiguous>1).sum()), "historical_rank_rows":0,
             "historical_position_ready":False,"metadata_is_current_not_historical":True,
             "paid_llm_calls":0,"credentials_read":False}
    outputs={p.name:{"sha256":sha(p),"bytes":p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()}
    dump_new(out/"snapshot_manifest.json",{"created_utc":now(),"scope_manifest_sha256":sha(store/"scope_manifest.json"),
             "summary":summary,"outputs":outputs,"requests":{str(p.relative_to(store)):sha(p) for p in sorted((store/"requests").glob("*.json"))}})
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    print("Snapshot:",out,flush=True)
    return out


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=["scope","metadata","snapshot"])
    parser.add_argument("--source",type=Path,default=SOURCE)
    parser.add_argument("--store",type=Path,default=STORE)
    parser.add_argument("--limit",type=int)
    parser.add_argument("--workers",type=int,default=3)
    parser.add_argument("--max-requests",type=int,default=400)
    parser.add_argument("--interval",type=float,default=.75)
    parser.add_argument("--timeout",type=int,default=30)
    a=parser.parse_args(argv)
    require(1<=a.workers<=3 and 1<=a.max_requests<=450 and .5<=a.interval<=5 and 1<=a.timeout<=60,"Unsafe collector bounds")
    require(a.limit is None or 1<=a.limit<=100000,"Invalid limit")
    scope=prepare_scope(a.source,a.store)
    if a.phase=="scope":
        print(json.dumps(json.loads((a.store/"scope_manifest.json").read_text())["summary"],indent=2))
    if a.phase=="metadata":
        sent=fetch_metadata(scope,a.store,a.limit,a.workers,a.max_requests,a.interval,a.timeout)
        print("HTTP sends this run:",sent)
    if a.phase in ("metadata","snapshot"):
        snapshot(scope,a.store)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
