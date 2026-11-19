"""Action-only runtime utilities. Importing this file never sends a request."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import threading
from pathlib import Path

from common import MODULE, ROOT, assert_unchanged, read_json, sha256, utc
from baseline_features import fingerprint
from action_review import canonical, response_errors

ENDPOINT = "https://openrouter.ai/api/v1/responses"
DEFAULT_OUTPUT = MODULE/"action_review_model_c_v1"/"model_c_calibration100_luna_xhigh_v1.jsonl"
RUN_CODE = ("action_review_run.py", "run_action_review_model_c.py", "verify_action_review_run.py",
            "test_action_review_run.py", "ACTION_REVIEW_RUN_v1.md")
TRANSPORT_PATH = ROOT/"code/08_run_model_review.py"


def load_transport():
    # Import functions only. Never call the old main/review_one/validate_review.
    code = str(ROOT/"code")
    if code not in sys.path:
        sys.path.insert(0,code)
    spec = importlib.util.spec_from_file_location("nhb_action_http_transport",TRANSPORT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_builder=module.build_request_body
    def action_builder(args,messages,schema):
        body=original_builder(args,messages,schema)
        body["text"]["format"]["name"]="nhb_action_review_v1"
        return body
    module.build_request_body=action_builder
    return module


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Action-only fixed 100-paper calibration; no core classification")
    p.add_argument("--preparation-dir",type=Path,default=MODULE/"action_review_preparation_v1")
    p.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    p.add_argument("--model",default="openai/gpt-5.6-luna")
    p.add_argument("--reasoning-effort",choices=("low","medium","high","xhigh"),default="xhigh")
    p.add_argument("--api-key-env",default="OPENROUTER_API_KEY")
    selection = p.add_mutually_exclusive_group()
    selection.add_argument("--limit",type=int,default=5)
    selection.add_argument("--all",action="store_true")
    p.add_argument("--resume",action="store_true")
    p.add_argument("--max-api-calls",type=int,required=True)
    p.add_argument("--workers",type=int,default=2)
    p.add_argument("--timeout",type=float,default=600)
    p.add_argument("--http-retries",type=int,default=1)
    p.add_argument("--validation-retries",type=int,default=0)
    p.add_argument("--max-output-tokens",type=int,default=20000)
    p.add_argument("--dry-run",action="store_true")
    a = p.parse_args(argv)
    if (not 1<=a.limit<=100 or not 1<=a.max_api_calls<=400 or not 1<=a.workers<=8 or
        not 1<=a.timeout<=600 or a.http_retries not in (0,1) or a.validation_retries not in (0,1) or
        not 1000<=a.max_output_tokens<=30000):
        p.error("limit 1–100; cap 1–400; workers 1–8; timeout 1–600; retries 0–1; output 1000–30000")
    if not a.model.startswith("openai/") or any(c.isspace() for c in a.model):
        p.error("Use an explicit openai/... OpenRouter model identifier")
    a.endpoint=ENDPOINT
    a.provider="openrouter"
    a.resolved_api_style="responses"
    a.response_format="json_schema"
    a.thinking="none"
    a.temperature=None
    a.top_p=None
    return a


def output_paths(output):
    output = output.expanduser().absolute()
    if (output.suffix != ".jsonl" or output.is_symlink() or
        not output.resolve().is_relative_to(MODULE) or output.resolve().parent==MODULE):
        raise ValueError("Output must be a JSONL in a new module subdirectory")
    paths = {"validated":output,
        "errors":output.with_name(output.stem+".errors.jsonl"),
        "attempts":output.with_name(output.stem+".attempts.jsonl"),
        "lock":output.with_name(output.stem+".writer.lock"),
        "artifacts":output.with_name(output.stem+".artifacts")}
    for p in paths.values():
        if p.is_symlink():
            raise ValueError("Symlink output/sidecar not allowed")
    return paths


def read_rows(path, maximum=100000):
    rows=[]
    with path.open("rb") as handle:
        for n in range(maximum+1):
            line=handle.readline(2*1024*1024+1)
            if not line:
                break
            if n==maximum or len(line)>2*1024*1024 or not line.endswith(b"\n"):
                raise ValueError(f"Oversize/truncated JSONL {path}; inspect before resume")
            row=json.loads(line)
            if not isinstance(row,dict):
                raise ValueError("Expected JSONL object")
            rows.append(row)
    return rows


def load_preparation(directory):
    directory=directory.expanduser().absolute()
    if directory.is_symlink() or not directory.resolve().is_relative_to(MODULE):
        raise ValueError("Expected local preparation artifact")
    mp=directory/"preparation_manifest.json"
    vp=directory/"validation_report.json"
    m,v=read_json(mp),read_json(vp)
    if (m.get("schema_version")!="nhb-action-review-preparation-run-v1" or
        v.get("preparation_manifest_sha256")!=sha256(mp) or v.get("blockers")!=[] or
        not v.get("checks") or not all(v["checks"].values()) or
        v.get("ready_for_manual_calibration") is not True):
        raise ValueError("Validated matching action preparation required")
    inv=[fingerprint(mp),fingerprint(vp)]
    for name,rec in {**m["outputs"],**m["snapshots"]}.items():
        p=directory/name
        if not p.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Unsafe preparation artifact path")
        actual=fingerprint(p)
        if actual["sha256"]!=rec["sha256"] or actual["size_bytes"]!=rec["size_bytes"]:
            raise ValueError(f"Changed preparation artifact: {name}")
        inv.append(actual)
    # Pin the live action validator to the already reviewed preparation snapshot.
    for name in ("action_review.py","common.py","baseline_features.py"):
        if sha256(MODULE/name)!=m["snapshots"]["code_and_policy/"+name]["sha256"]:
            raise ValueError("Action validator changed since preparation; use a reviewed new version")
    packets=read_rows(directory/"action_calibration_100_inputs_blinded_v1.jsonl",100)
    selection=read_json(directory/"action_calibration_selection_v1.json")
    ids=[p.get("work_id") for p in packets]
    if len(ids)!=100 or len(set(ids))!=100 or ids!=selection["work_ids"]:
        raise ValueError("Exactly the frozen 100 calibration records are required")
    if canonical(ids)!=selection["ordered_work_id_sha256"]:
        raise ValueError("Calibration order hash differs")
    for packet in packets:
        if packet.get("action_review_eligible") is not True or canonical(packet)!=selection["input_record_sha256"][packet["work_id"]]:
            raise ValueError("Changed/ineligible calibration packet")
    prompt_path=directory/"code_and_policy/action_review_prompt_v1.txt"
    schema_path=directory/"action_only_output_schema_v1.json"
    prompt=prompt_path.read_text(encoding="utf-8")
    schema=read_json(schema_path)
    code_paths=[MODULE/n for n in RUN_CODE]+[MODULE/n for n in ("action_review.py","common.py","baseline_features.py")]
    code_paths += [TRANSPORT_PATH,ROOT/"code/fulltext_pipeline/common.py",
                   ROOT/"code/fulltext_pipeline/model_review_support.py",ROOT/"uv.lock",ROOT/"pyproject.toml"]
    code_inv=[fingerprint(p) for p in code_paths]
    assert_unchanged(inv+code_inv)
    return packets,prompt,schema,inv,code_inv


def signature(args,inv,code_inv):
    hashes={Path(r["path"]).name:r["sha256"] for r in inv}
    return {"schema_version":"nhb-action-run-signature-v1","provider":"openrouter",
        "endpoint":ENDPOINT,"api_style":"responses","model":args.model,
        "reasoning_effort":args.reasoning_effort,"max_output_tokens":args.max_output_tokens,
        "http_retries":args.http_retries,"validation_retries":args.validation_retries,
        "timeout_seconds":args.timeout,"response_format":"json_schema",
        "preparation_manifest_sha256":hashes["preparation_manifest.json"],
        "input_file_sha256":hashes["action_calibration_100_inputs_blinded_v1.jsonl"],
        "prompt_sha256":hashes["action_review_prompt_v1.txt"],
        "schema_sha256":hashes["action_only_output_schema_v1.json"],
        "code_and_dependencies_sha256":canonical([{ "path":str(Path(r["path"]).relative_to(ROOT)),
            "sha256":r["sha256"]} for r in code_inv])}


def completed(path,packets,sig):
    if not path.exists():
        return set()
    byid={p["work_id"]:p for p in packets}
    done=set()
    for row in read_rows(path,100):
        wid=row.get("work_id")
        if wid in done or wid not in byid or row.get("run_signature")!=sig or row.get("input_packet_sha256")!=canonical(byid[wid]):
            raise ValueError(f"Cannot resume {wid}: duplicate/unknown ID or settings/input changed")
        if row.get("ok") is not True or response_errors(row.get("response"),byid[wid]):
            raise ValueError(f"Cannot resume {wid}: output is not valid action-only result")
        if row.get("decision_status")!="model_suggestion_pending_human_calibration":
            raise ValueError("Model suggestion must not masquerade as human adjudication")
        done.add(wid)
    return done


def fatal_attempts(attempts):
    return any(r.get("http_status") in (401,402,403) for r in attempts)


def reported_cost(attempts):
    total=0.0; reported=0
    for a in attempts:
        cost=(a.get("usage") or {}).get("cost")
        if type(cost) in (int,float) and math.isfinite(cost) and cost>=0:
            total+=cost; reported+=1
    return {"reported_cost_usd":total if reported else None,"attempts_with_cost":reported,
        "cost_reporting_complete":reported==len(attempts) and bool(attempts),
        "unreported_cost":"unknown_not_zero; consult provider billing"}


class Journal:
    def __init__(self,handle,transport,key):
        self.handle=handle; self.transport=transport; self.key=key
        self.finished=[]; self.events=[]; self.lock=threading.Lock()

    def emit(self,event):
        event=self.transport.clean_log_value(dict(logged_at_utc=utc(),**event),self.key)
        with self.lock:
            self.handle.write(json.dumps(event,ensure_ascii=False,allow_nan=False)+"\n")
            self.handle.flush(); os.fsync(self.handle.fileno())
            self.events.append(event)
            if event["event"]=="request_finished": self.finished.append(event)


def review_one(packet,args,prompt,schema,transport,budget,audit,sig,run_id,stop):
    attempts=[]; history=[]; result=None; payload={}; raw=""; error=None
    context={"run_id":run_id,"work_id":packet["work_id"],"review_id":packet["review_id"],
             "provider":"openrouter","model":args.model,"input_packet_sha256":canonical(packet)}
    messages=[{"role":"system","content":prompt},{"role":"user","content":json.dumps(packet,ensure_ascii=False,separators=(",",":"))}]
    try:
        for round_number in range(args.validation_retries+1):
            if stop.is_set(): raise RuntimeError("Dispatch stopped before next request")
            payload,number=transport.request_completion(args=args,api_key=audit.key,messages=messages,
                budget=budget,record_attempts=attempts,audit=audit,context=context,
                validation_round=round_number,schema=schema)
            state_errors=transport.completion_state_errors(payload,"responses")
            try:
                raw=transport.response_text(payload,"responses")
                result=transport.parse_json_object(raw)
                errors=state_errors+response_errors(result,packet)
            except (ValueError,TypeError,KeyError) as exc:
                errors=state_errors+[f"Action response parse/validation error: {exc}"]
            entry={"attempt_number":number,"validation_round":round_number,"valid":not errors,"errors":errors}
            history.append(entry)
            audit.emit(dict(event="action_validation_result",**context,**entry))
            if not errors:
                error=None; break
            error="Action-only response failed validation"
            # No failed assistant answer is used as new evidence in a repair.
            if round_number<args.validation_retries:
                messages.append({"role":"user","content":"Return a complete corrected action-only object using only the original evidence. Do not fabricate support. Local errors: "+json.dumps(errors[:12],ensure_ascii=False)})
    except Exception as exc:
        error=str(exc)
    if fatal_attempts(attempts): stop.set()
    usage,accounting=transport.aggregate_usage(attempts)
    row={"schema_version":"nhb-action-model-envelope-v1",**context,"completed_at_utc":utc(),
        "run_signature":sig,"ok":error is None and result is not None,
        "decision_status":"model_suggestion_pending_human_calibration",
        "api_calls":len(attempts),"api_usage":usage,"usage_accounting":accounting,
        "cost_accounting":reported_cost(attempts),"validation_history":history,
        "provider_response_metadata":transport.provider_response_metadata(payload),
        "reported_usage_raw":payload.get("usage"),"completion_state":transport.completion_state(payload,"responses")}
    if row["ok"]: row["response"]=result
    else: row.update(error=error or "No result",candidate_response=result,visible_response_text=raw)
    # All visible output, including invalid JSON, is archived, not just excerpts.
    audit.emit(dict(event="visible_response_snapshot",**context,visible_response_text=raw,
        provider_response_metadata=transport.provider_response_metadata(payload),reported_usage_raw=payload.get("usage")))
    return transport.clean_log_value(row,audit.key)
