#!/usr/bin/env python3
"""Run blinded AlphaFold reviews through audited model-provider endpoints.

The command is deliberately conservative: it freezes five input slots by
default, retains forced-U slots without an API call, and requires an explicit
API-call cap. Every response is checked locally; each HTTP attempt and repair
is audited. DeepSeek/GLM Chat Completions and OpenAI-compatible Responses
(including OpenRouter) use distinct, validated request shapes. Resume requires
matching input and model/protocol fingerprints.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import os
import platform
import sys
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from jsonschema import Draft202012Validator
from tqdm import tqdm

from fulltext_pipeline.common import PROJECT_ROOT, redact_sensitive_text
from fulltext_pipeline.model_review_support import (
    fingerprint, prepare_packet, semantic_errors, source_texts,
)


DEFAULT_INPUT = (
    PROJECT_ROOT / "fulltext" / "pilot" / "model_inputs_v3" / "pilot_model_inputs.jsonl"
)
DEFAULT_PROMPT = PROJECT_ROOT / "config" / "af_review_prompt_v2.txt"
DEFAULT_SCHEMA = PROJECT_ROOT / "config" / "af_review_output_schema_v2.json"
RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
REASONING_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--provider", required=True, help="Stable name used in output metadata")
    parser.add_argument("--endpoint", required=True, help="Full HTTPS API endpoint URL")
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--api-style",
        choices=("auto", "chat_completions", "responses"),
        default="auto",
        help="Protocol dialect; auto infers it from the endpoint path",
    )
    parser.add_argument(
        "--api-key-env",
        required=True,
        help="Environment variable containing the API key; never pass the key itself",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--errors", type=Path)
    parser.add_argument("--attempts", type=Path, help="Append-only per-attempt event journal")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Immutable per-invocation audit bundles; defaults beside --output",
    )
    parser.add_argument("--work-id", action="append", default=[], help="Restrict to these fixed IDs; repeat for a cohort")

    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--limit", type=int, default=5, help="Freeze this many input slots before eligibility/resume filtering")
    selection.add_argument("--all", action="store_true")
    parser.add_argument(
        "--pending-limit",
        type=int,
        help="With --all, process only this many currently pending API-eligible records per invocation",
    )

    existing = parser.add_mutually_exclusive_group()
    existing.add_argument("--resume", action="store_true")
    existing.add_argument("--force", action="store_true")

    parser.add_argument(
        "--max-api-calls",
        type=int,
        required=True,
        help="Hard cap including HTTP retries and invalid-output repair calls",
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--http-retries", type=int, default=2)
    parser.add_argument("--validation-retries", type=int, default=1)
    parser.add_argument("--max-output-tokens", type=int, default=1600)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--top-p", type=float)
    parser.add_argument(
        "--thinking", choices=("auto", "none", "disabled", "enabled"), default="auto",
        help="Provider thinking toggle; reasoning effort remains a separate setting",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        help="Explicit provider reasoning level; required for known reasoning models",
    )
    parser.add_argument(
        "--response-format",
        choices=("none", "json_object", "json_schema"),
        default="json_object",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.epilog = (
        "--limit freezes input slots BEFORE eligibility/resume filtering. "
        "--pending-limit, used with --all, is applied AFTER completed-record filtering "
        "and therefore advances safely across --resume runs."
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_run_manifest(path: Path, value: dict[str, Any]) -> None:
    atomic_write_json(path, value)
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    checksum = f"{sha256_bytes(path.read_bytes())}  {path.name}\n"
    temporary = checksum_path.with_suffix(checksum_path.suffix + ".part")
    temporary.write_text(checksum, encoding="ascii")
    temporary.replace(checksum_path)


def package_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def provenance_source_paths() -> list[Path]:
    code_root = Path(__file__).resolve().parent
    candidates = [
        Path(__file__).resolve(),
        code_root / "07_build_model_packets.py",
        code_root / "05_extract_af_contexts.py",
        code_root / "10_verify_model_run_artifact.py",
        code_root / "11_run_pilot_calibration_v3.sh",
        code_root / "12_revalidate_model_attempts.py",
        code_root / "13_run_pilot_calibration_v4.sh",
        code_root / "15_run_pilot_v4.sh",
        code_root / "17_build_pilot_adjudication.py",
        code_root / "18_run_pilot_model_c_v4_1.sh",
        code_root / "19_run_pilot_model_c_openrouter_v4_2.sh",
        code_root / "20_run_pilot_model_c_openrouter_v4_3.sh",
        code_root / "33_build_full_model_packets.py",
        code_root / "34_check_full_run_readiness.py",
        code_root / "fulltext_pipeline" / "agreement_policy.py",
        code_root / "fulltext_pipeline" / "model_review_support.py",
        code_root / "fulltext_pipeline" / "common.py",
        code_root / "tests" / "test_model_review.py",
        PROJECT_ROOT / "config" / "af_production_protocol_v1.json",
        PROJECT_ROOT / "pyproject.toml",
        PROJECT_ROOT / "uv.lock",
    ]
    return [path for path in candidates if path.is_file()]


def protocol_source_paths() -> list[Path]:
    excluded = {
        "10_verify_model_run_artifact.py",
        "12_revalidate_model_attempts.py",
        "test_model_review.py",
    }
    return [
        path
        for path in provenance_source_paths()
        if (
            path.suffix == ".py"
            or path.name == "af_production_protocol_v1.json"
        )
        and path.name not in excluded
    ]


def protocol_code_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        try:
            identity = path.resolve().relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            identity = Path(path.name)
        digest.update(str(identity).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def snapshot_file(
    *, source: Path, destination: Path, artifact_dir: Path, shared_root: Path | None = None
) -> dict[str, Any]:
    data = source.read_bytes()
    digest = sha256_bytes(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    storage = "independent_copy"
    if shared_root is not None:
        shared = shared_root / digest / source.name
        shared.parent.mkdir(parents=True, exist_ok=True)
        if not shared.exists():
            temporary = shared.with_name(shared.name + f".{uuid.uuid4().hex}.part")
            temporary.write_bytes(data)
            try:
                temporary.replace(shared)
            except OSError:
                temporary.unlink(missing_ok=True)
        if sha256_bytes(shared.read_bytes()) != digest:
            raise ValueError(f"Shared snapshot hash mismatch: {shared}")
        try:
            os.link(shared, destination)
            storage = "content_addressed_hardlink"
        except OSError:
            destination.write_bytes(data)
    else:
        destination.write_bytes(data)
    return {
        "original_path": str(source.resolve()),
        "snapshot_path": str(destination.relative_to(artifact_dir)),
        "sha256": digest,
        "bytes": len(data),
        "storage": storage,
    }


def create_run_artifact(
    *,
    args: argparse.Namespace,
    run_id: str,
    signature: dict[str, Any],
    scope: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    forced: list[dict[str, Any]],
) -> tuple[Path, Path, dict[str, Any]]:
    artifact_root = args.artifacts_dir or args.output.with_name(args.output.stem + ".artifacts")
    artifact_dir = artifact_root / run_id
    artifact_dir.mkdir(parents=True, exist_ok=False)
    # Keep the content-addressed store beside (not inside) the per-run bundle
    # directory so bundle enumeration and verification continue to see only
    # immutable invocation directories.
    shared_root = artifact_root.parent / "_shared_model_run_snapshots"

    snapshots: dict[str, Any] = {}
    snapshots["input"] = snapshot_file(
        source=args.input,
        destination=artifact_dir / "input" / args.input.name,
        artifact_dir=artifact_dir,
        shared_root=shared_root,
    )
    adjacent_meta = args.input.with_suffix(".meta.json")
    if adjacent_meta.is_file():
        snapshots["input_metadata"] = snapshot_file(
            source=adjacent_meta,
            destination=artifact_dir / "input" / adjacent_meta.name,
            artifact_dir=artifact_dir,
            shared_root=shared_root,
        )
    snapshots["prompt"] = snapshot_file(
        source=args.prompt,
        destination=artifact_dir / "protocol" / args.prompt.name,
        artifact_dir=artifact_dir,
        shared_root=shared_root,
    )
    snapshots["schema"] = snapshot_file(
        source=args.schema,
        destination=artifact_dir / "protocol" / args.schema.name,
        artifact_dir=artifact_dir,
        shared_root=shared_root,
    )
    source_snapshots = []
    protocol_sources = {path.resolve() for path in protocol_source_paths()}
    for source in provenance_source_paths():
        try:
            relative = source.resolve().relative_to(PROJECT_ROOT.resolve())
        except ValueError:
            relative = Path(source.name)
        source_snapshot = snapshot_file(
            source=source,
            destination=artifact_dir / "source" / relative,
            artifact_dir=artifact_dir,
            shared_root=shared_root,
        )
        source_snapshot["protocol_code"] = source.resolve() in protocol_sources
        source_snapshots.append(source_snapshot)
    snapshots["source_and_locks"] = source_snapshots

    manifest = {
        "schema_version": "af-model-run-manifest-v1",
        "run_id": run_id,
        "status": "running",
        "started_at_utc": utc_now(),
        "provider": args.provider,
        "requested_model": args.model,
        "endpoint": args.endpoint,
        "run_signature": signature,
        "execution": {
            "workers": args.workers,
            "timeout_seconds": args.timeout,
            "http_retries": args.http_retries,
            "validation_retries": args.validation_retries,
            "max_api_calls": args.max_api_calls,
            "selection": "all" if args.all else "limit",
            "limit": None if args.all else args.limit,
            "pending_limit": args.pending_limit,
            "requested_work_ids": args.work_id,
            "api_key_env_name": args.api_key_env,
        },
        "scope": {
            "work_ids": [packet["work_id"] for packet in scope],
            "api_work_ids": [packet["work_id"] for packet in selected],
            "forced_u_work_ids": [packet["work_id"] for packet in forced],
        },
        "environment": {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "packages": {
                name: package_version(name)
                for name in ("requests", "jsonschema", "tqdm")
            },
        },
        "snapshots": snapshots,
        "output_targets": {
            "validated": str(args.output.resolve()),
            "errors": str((args.errors or args.output.with_name(args.output.stem + ".errors.jsonl")).resolve()),
            "attempts": str((args.attempts or args.output.with_name(args.output.stem + ".attempts.jsonl")).resolve()),
            "forced_u": str(args.output.with_name(args.output.stem + ".forced_u.jsonl").resolve()),
        },
        "model_identity_note": (
            "requested_model is an API identifier and may be a mutable alias; an immutable backend "
            "revision is known only when the provider returns one in response metadata"
        ),
        "security_and_retention": {
            "api_key_persisted": False,
            "hidden_reasoning_content_persisted": False,
            "hidden_reasoning_token_counts_persisted_when_reported": True,
            "final_structured_response_persisted": True,
            "sanitized_request_bodies_persisted": True,
            "visible_provider_response_text_persisted": True,
            "failed_envelope_response_excerpt_limit_characters": 2000,
            "full_visible_invalid_response_retained_in_attempt_journal": True,
        },
    }
    manifest_path = artifact_dir / "run_manifest.json"
    write_run_manifest(manifest_path, manifest)
    return artifact_dir, manifest_path, manifest


def archive_run_records(
    *, artifact_dir: Path, run_id: str, sources: dict[str, Path]
) -> dict[str, Any]:
    archived: dict[str, Any] = {}
    for label, source in sources.items():
        records = (
            [record for record in read_jsonl(source) if record.get("run_id") == run_id]
            if source.exists()
            else []
        )
        destination = artifact_dir / "records" / f"{label}.jsonl"
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ).encode("utf-8")
        destination.write_bytes(content)
        archived[label] = {
            "snapshot_path": str(destination.relative_to(artifact_dir)),
            "sha256": sha256_bytes(content),
            "bytes": len(content),
            "records": len(records),
        }
    return archived


def provider_response_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "response_id": payload.get("request_id") or payload.get("id"),
        "reported_model": payload.get("model"),
        "system_fingerprint": payload.get("system_fingerprint"),
        "created": payload.get("created"),
        "service_tier": payload.get("service_tier"),
        # One OpenRouter model slug can route to multiple upstream providers.
        # This object is returned only when router metadata was requested.
        "openrouter_metadata": payload.get("openrouter_metadata"),
    }
    return {key: value for key, value in fields.items() if value is not None}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            records.append(record)
    return records


def load_completed_work_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for record in read_jsonl(path):
        work_id = record.get("work_id")
        if work_id:
            completed.add(str(work_id))
    return completed


class CallBudget:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.used = 0
        self._lock = threading.Lock()

    def reserve(self) -> int | None:
        with self._lock:
            if self.used >= self.maximum:
                return None
            self.used += 1
            return self.used


def compact_schema(schema: dict[str, Any]) -> str:
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def make_system_message(
    prompt: str, schema: dict[str, Any], *, embed_schema: bool = True
) -> str:
    if not embed_schema:
        return prompt.rstrip()
    return (
        prompt.rstrip()
        + "\n\nThe response must validate against this JSON Schema:\n"
        + compact_schema(schema)
    )


def model_slug_name(model: str) -> str:
    """Return a model name without an OpenRouter namespace or modifier."""
    normalized = model.casefold().rsplit("/", 1)[-1]
    return normalized.split(":", 1)[0]


def model_family(model: str) -> str:
    normalized = model_slug_name(model)
    if normalized.startswith("deepseek-"):
        return "deepseek"
    if normalized.startswith("glm-"):
        return "glm"
    if normalized.startswith("gpt-"):
        return "openai"
    return "generic"


def resolve_api_style(endpoint: str, requested: str) -> str:
    if requested != "auto":
        return requested
    path = urlsplit(endpoint).path.rstrip("/").casefold()
    return "responses" if path.endswith("/responses") else "chat_completions"


def effective_thinking(args: argparse.Namespace) -> str:
    if args.thinking != "auto":
        return args.thinking
    return "enabled" if args.provider_family in {"deepseek", "glm"} else "none"


def remote_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Translate the local Draft 2020-12 schema to the strict API subset.

    Draft 2020-12 permits ``const`` and ``enum`` to imply a value type. OpenAI's
    strict structured-output validator requires that type to be explicit and
    rejects some otherwise-valid keywords. The local schema remains the
    authoritative validation contract and is not modified; only the copy sent
    to the provider is normalized. Removed constraints are still enforced by
    :func:`validate_review` after generation.
    """

    def json_type(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        raise TypeError(f"Unsupported JSON Schema literal type: {type(value).__name__}")

    unsupported_keywords = {"uniqueItems", "minLength", "maxLength"}

    def normalize(node: Any) -> Any:
        if isinstance(node, list):
            return [normalize(item) for item in node]
        if not isinstance(node, dict):
            return node
        result = {
            key: normalize(value)
            for key, value in node.items()
            if key not in unsupported_keywords
        }
        if "type" not in result:
            literals: list[Any] = []
            if "const" in result:
                literals = [result["const"]]
            elif isinstance(result.get("enum"), list) and result["enum"]:
                literals = result["enum"]
            if literals:
                inferred = list(dict.fromkeys(json_type(value) for value in literals))
                result["type"] = inferred[0] if len(inferred) == 1 else inferred
        return result

    result = json.loads(json.dumps(schema))
    result.pop("$schema", None)
    result.pop("$id", None)
    return normalize(result)


def build_request_body(
    args: argparse.Namespace,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
) -> dict[str, Any]:
    if args.resolved_api_style == "responses":
        system_parts = [item["content"] for item in messages if item["role"] == "system"]
        input_items = [item for item in messages if item["role"] != "system"]
        body: dict[str, Any] = {
            "model": args.model,
            "input": input_items,
            "max_output_tokens": args.max_output_tokens,
            "stream": False,
            "store": False,
        }
        if system_parts:
            body["instructions"] = "\n\n".join(system_parts)
        if args.reasoning_effort:
            body["reasoning"] = {"effort": args.reasoning_effort}
        if args.response_format == "json_schema":
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "af_model_review_v2",
                    "strict": True,
                    "schema": remote_json_schema(schema),
                }
            }
        elif args.response_format == "json_object":
            body["text"] = {"format": {"type": "json_object"}}
        if args.temperature is not None:
            body["temperature"] = args.temperature
        if args.top_p is not None:
            body["top_p"] = args.top_p
        if args.provider.casefold() == "openrouter":
            # Prevent a routed backend from silently ignoring strict schema or
            # reasoning parameters required by this audited profile.
            body["provider"] = {"require_parameters": True}
        return body

    body = {
        "model": args.model,
        "messages": messages,
        "max_tokens": args.max_output_tokens,
        "stream": False,
    }
    if args.response_format in {"json_object", "json_schema"}:
        # DeepSeek and GLM expose JSON mode here; local Draft 2020-12
        # validation remains authoritative for the complete scientific schema.
        body["response_format"] = {"type": "json_object"}
    thinking = effective_thinking(args)
    if thinking != "none":
        body["thinking"] = {"type": thinking}
    if args.reasoning_effort:
        body["reasoning_effort"] = args.reasoning_effort
    if args.temperature is not None:
        body["temperature"] = args.temperature
    if args.top_p is not None:
        body["top_p"] = args.top_p
    return body


def request_headers(args: argparse.Namespace, api_key: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if args.provider.casefold() == "openrouter":
        headers["X-OpenRouter-Metadata"] = "enabled"
    return headers


def response_text(payload: dict[str, Any], api_style: str = "chat_completions") -> str:
    if api_style == "responses":
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct:
            return direct
        parts: list[str] = []
        for item in payload.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        if parts:
            return "".join(parts)
        raise ValueError("Responses payload has no output_text message content")

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Response has no choices[0].message.content") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        if any(parts):
            return "".join(parts)
    raise ValueError("Response content is not a string")


def completion_state(payload: dict[str, Any], api_style: str) -> dict[str, Any]:
    if api_style == "responses":
        return {
            "response_status": payload.get("status"),
            "finish_reason": None,
            "incomplete_details": payload.get("incomplete_details"),
        }
    try:
        finish_reason = payload["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError):
        finish_reason = None
    return {
        "response_status": None,
        "finish_reason": finish_reason,
        "incomplete_details": None,
    }


def completion_state_errors(payload: dict[str, Any], api_style: str) -> list[str]:
    state = completion_state(payload, api_style)
    if api_style == "responses":
        if state["response_status"] not in {None, "completed"}:
            return [
                "response incomplete: status="
                f"{state['response_status']!r}, details={state['incomplete_details']!r}"
            ]
        if state["incomplete_details"]:
            return [f"response incomplete: {state['incomplete_details']!r}"]
        return []
    if state["finish_reason"] not in {None, "stop"}:
        return [f"response incomplete: finish_reason={state['finish_reason']!r}"]
    return []


def parse_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(candidate[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Model response must be one JSON object")
    return value


def exact_source_texts(packet: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    return source_texts(packet, evidence)


def validate_review(
    review: dict[str, Any], packet: dict[str, Any], validator: Draft202012Validator
) -> list[str]:
    errors = [
        f"schema {list(error.absolute_path)}: {error.message}"
        for error in sorted(validator.iter_errors(review), key=lambda item: tuple(map(str, item.path)))
    ]
    if errors:
        return errors  # Do not dereference malformed evidence/action objects.
    if review.get("review_id") != packet.get("review_id"):
        errors.append("review_id does not match the input packet")
    if review.get("work_id") != packet.get("work_id"):
        errors.append("work_id does not match the input packet")

    for index, evidence in enumerate(review.get("evidence", [])):
        quote = evidence.get("quote", "")
        if len(quote.split()) > 25:
            errors.append(f"evidence[{index}].quote exceeds 25 whitespace-delimited words")
        source_kind = evidence.get("source_kind")
        block_index = evidence.get("block_index")
        if source_kind == "fulltext_block" and not isinstance(block_index, int):
            errors.append(f"evidence[{index}] fulltext_block requires an integer block_index")
        if source_kind != "fulltext_block" and block_index is not None:
            errors.append(f"evidence[{index}] non-fulltext source requires block_index=null")
        source_texts = exact_source_texts(packet, evidence)
        if not source_texts:
            errors.append(f"evidence[{index}] source location was not found in the input")
        elif quote and not any(quote in source_text for source_text in source_texts):
            errors.append(f"evidence[{index}].quote is not an exact substring of its source")
        if source_kind == "fulltext_block":
            sections = [b.get("section") for b in packet.get("input_material", {}).get("evidence_blocks", [])
                        if b.get("index") == block_index]
            if evidence.get("section") not in sections:
                errors.append(f"evidence[{index}].section does not match the source block")
    if review.get("schema_version") == "af-model-review-output-v2":
        errors.extend(semantic_errors(review, packet))
    return errors


def clean_log_value(value: Any, secret: str) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value.replace(secret, "[REDACTED]") if secret else value)
    if isinstance(value, list):
        return [clean_log_value(item, secret) for item in value]
    if isinstance(value, dict):
        return {key: clean_log_value(item, secret) for key, item in value.items()}
    return value


class AttemptAudit:
    """Thread-safe event journal; usage appears only on request_finished events."""

    def __init__(self, handle: Any, secret: str) -> None:
        self.handle = handle
        self.secret = secret
        self.finished: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, event: dict[str, Any]) -> None:
        safe = clean_log_value({"logged_at_utc": utc_now(), **event}, self.secret)
        with self._lock:
            self.handle.write(json.dumps(safe, ensure_ascii=False) + "\n")
            self.handle.flush()
            if safe["event"] == "request_finished":
                self.finished.append(safe)


def retry_after_seconds(headers: Any) -> float | None:
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(str(value))
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def usage_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def nested_usage_int(usage: dict[str, Any], parent: str, child: str) -> int | None:
    details = usage.get(parent)
    if not isinstance(details, dict):
        return None
    return usage_int(details.get(child))


def normalize_usage(usage: dict[str, Any]) -> dict[str, int]:
    """Normalize Chat Completions and Responses token fields without guessing."""
    if not isinstance(usage, dict):
        return {}
    input_tokens = usage_int(usage.get("input_tokens"))
    if input_tokens is None:
        input_tokens = usage_int(usage.get("prompt_tokens"))
    output_tokens = usage_int(usage.get("output_tokens"))
    if output_tokens is None:
        output_tokens = usage_int(usage.get("completion_tokens"))
    values = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": usage_int(usage.get("total_tokens")),
        "cached_input_tokens": (
            nested_usage_int(usage, "input_tokens_details", "cached_tokens")
            if "input_tokens_details" in usage
            else nested_usage_int(usage, "prompt_tokens_details", "cached_tokens")
        ),
        "cache_write_tokens": nested_usage_int(
            usage, "input_tokens_details", "cache_write_tokens"
        ),
        "reasoning_tokens": (
            nested_usage_int(usage, "output_tokens_details", "reasoning_tokens")
            if "output_tokens_details" in usage
            else nested_usage_int(usage, "completion_tokens_details", "reasoning_tokens")
        ),
        "prompt_cache_hit_tokens": usage_int(usage.get("prompt_cache_hit_tokens")),
        "prompt_cache_miss_tokens": usage_int(usage.get("prompt_cache_miss_tokens")),
    }
    return {key: value for key, value in values.items() if value is not None}


def aggregate_usage(attempts: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, Any]]:
    totals: dict[str, int] = {}
    reported = 0
    fully_reported = 0
    for attempt in attempts:
        usage = attempt.get("usage") or {}
        values = attempt.get("normalized_usage") or normalize_usage(usage)
        reported += bool(values)
        fully_reported += all(
            key in values for key in ("input_tokens", "output_tokens", "total_tokens")
        )
        for key, value in values.items():
            totals[key] = totals.get(key, 0) + value
    accounting = {
        "http_attempts": len(attempts),
        "attempts_with_reported_usage": reported,
        "attempts_without_reported_usage": len(attempts) - reported,
        "reporting_complete": fully_reported == len(attempts),
        "scope": "all HTTP attempts in this record/run, including invalid outputs and retries; unreported usage is unknown, not zero",
    }
    return totals, accounting


def request_completion(
    *,
    args: argparse.Namespace,
    api_key: str,
    messages: list[dict[str, str]],
    budget: CallBudget,
    record_attempts: list[dict[str, Any]],
    audit: AttemptAudit,
    context: dict[str, Any],
    validation_round: int,
    schema: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    body = build_request_body(args, messages, schema)

    for retry in range(args.http_retries + 1):
        call_number = budget.reserve()
        if call_number is None:
            raise RuntimeError("API call budget exhausted")
        started = time.monotonic()
        attempt = {
            **context,
            "attempt_number": call_number,
            "record_attempt_number": len(record_attempts) + 1,
            "validation_round": validation_round,
            "http_retry_number": retry,
            "purpose": "initial" if validation_round == 0 else "validation_repair",
            "http_status": None,
            "usage": {},
            "normalized_usage": {},
            "request_body_sha256": fingerprint(body),
        }
        audit.emit({"event": "request_started", **attempt, "request_body": body})
        payload: dict[str, Any] = {}
        failure: Exception | None = None
        retryable = False
        try:
            # No implicit redirect sends outside the explicit request budget.
            response = requests.post(
                args.endpoint,
                headers=request_headers(args, api_key),
                json=body,
                timeout=args.timeout,
                allow_redirects=False,
            )
            attempt["http_status"] = response.status_code
            attempt["response_request_id"] = response.headers.get("x-request-id")
            attempt["response_generation_id"] = response.headers.get("x-generation-id")
            attempt["retry_after_seconds"] = retry_after_seconds(response.headers)
            json_error: Exception | None = None
            try:
                value = response.json()
                if not isinstance(value, dict):
                    raise ValueError("API response is not a JSON object")
                payload = value
                if isinstance(payload.get("usage"), dict):
                    attempt["usage"] = payload["usage"]
                    attempt["normalized_usage"] = normalize_usage(payload["usage"])
                attempt["provider_response_id"] = payload.get("request_id") or payload.get("id")
                attempt["provider_response_metadata"] = provider_response_metadata(payload)
                attempt.update(completion_state(payload, args.resolved_api_style))
                try:
                    visible_text = response_text(payload, args.resolved_api_style)
                except (KeyError, IndexError, TypeError, ValueError):
                    visible_text = ""
                if visible_text:
                    attempt["visible_response_text"] = visible_text
                    attempt["visible_response_sha256"] = sha256_bytes(
                        visible_text.encode("utf-8")
                    )
            except (ValueError, requests.RequestException) as exc:
                json_error = exc
            if not 200 <= response.status_code < 300:
                failure = RuntimeError(f"HTTP {response.status_code}: {response.text[:1000]}")
                retryable = response.status_code in RETRYABLE_STATUS_CODES
            elif json_error is not None:
                failure = ValueError(f"Invalid API JSON: {json_error}")
                retryable = True
            if failure is None:
                attempt["outcome"] = "response_received"
            else:
                attempt["outcome"] = "http_error" if not 200 <= response.status_code < 300 else "api_json_error"
        except requests.RequestException as exc:
            failure = exc
            retryable = True
            attempt["outcome"] = "network_error"
        except Exception as exc:
            failure = exc
            attempt["outcome"] = "request_error"
        attempt["duration_seconds"] = round(time.monotonic() - started, 3)
        attempt["will_retry"] = bool(failure and retryable and retry < args.http_retries)
        if failure:
            attempt["error"] = str(failure)[:2000]
        record_attempts.append(clean_log_value(attempt, api_key))
        audit.emit({"event": "request_finished", **attempt})
        if failure is None:
            return payload, call_number
        if not attempt["will_retry"]:
            raise failure
        delay = attempt.get("retry_after_seconds")
        time.sleep(min(float(delay) if delay is not None else 2**retry, 60.0))
    raise RuntimeError("HTTP retry loop exhausted")


def review_one(
    *,
    packet: dict[str, Any],
    args: argparse.Namespace,
    api_key: str,
    system_message: str,
    schema: dict[str, Any],
    validator: Draft202012Validator,
    budget: CallBudget,
    run_id: str,
    audit: AttemptAudit,
    signature: dict[str, Any],
    artifact_reference: str,
) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": json.dumps(packet, ensure_ascii=False, separators=(",", ":"))},
    ]
    context = {
        "run_id": run_id,
        "provider": args.provider,
        "model": args.model,
        "review_id": packet["review_id"],
        "work_id": packet["work_id"],
        "input_packet_sha256": fingerprint(packet),
    }
    attempts: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    validation_history: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    raw_text = ""

    def envelope() -> dict[str, Any]:
        usage, accounting = aggregate_usage(attempts)
        return {
            "schema_version": "af-model-run-envelope-v3",
            **context,
            "completed_at_utc": utc_now(),
            "endpoint_host": urlsplit(args.endpoint).netloc,
            "run_artifact": artifact_reference,
            "run_signature": signature,
            "evidence_tier": packet["evidence_tier"],
            "estimated_input_tokens": packet.get("estimated_input_tokens"),
            "api_calls": len(attempts),
            "api_usage": usage,
            "usage_accounting": accounting,
            "final_response_usage": payload.get("usage", {}),
            "final_response_normalized_usage": normalize_usage(payload.get("usage", {})),
            "provider_response_metadata": provider_response_metadata(payload),
            "validation_history": validation_history,
        }

    try:
        for validation_round in range(args.validation_retries + 1):
            payload, call_number = request_completion(
                args=args, api_key=api_key, messages=messages, budget=budget,
                record_attempts=attempts, audit=audit, context=context,
                validation_round=validation_round, schema=schema,
            )
            raw_text = ""
            state_errors = completion_state_errors(payload, args.resolved_api_style)
            try:
                raw_text = response_text(payload, args.resolved_api_style)
                review = parse_json_object(raw_text)
                validation_errors = state_errors + validate_review(review, packet, validator)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                review = {}
                validation_errors = state_errors + [f"response parsing: {exc}"]
            validation = {
                "attempt_number": call_number,
                "validation_round": validation_round,
                "valid": not validation_errors,
                "errors": validation_errors[:20],
            }
            validation_history.append(validation)
            audit.emit({
                "event": "validation_result", **context, **validation,
                "response_excerpt": raw_text[:2000] if validation_errors else None,
            })
            if not validation_errors:
                return clean_log_value({**envelope(), "response": review}, api_key)
            if validation_round < args.validation_retries:
                repair_parts = [
                    "The previous response failed local validation. Correct it using only the supplied evidence.",
                    "Do not fabricate evidence to satisfy a rule; use uncertainty where appropriate.",
                ]
                if state_errors:
                    repair_parts.append(
                        "The previous generation was truncated. Keep the new analysis concise and "
                        "prioritize returning one complete JSON object within the token limit."
                    )
                if any("quote is not an exact substring" in error for error in validation_errors):
                    repair_parts.append(
                        "Replace every non-exact quote with a verbatim substring copied from its declared "
                        "source, preserving punctuation, spelling, and Unicode hyphens exactly."
                    )
                if any("quote exceeds 25" in error for error in validation_errors):
                    repair_parts.append(
                        "Shorten the overlong excerpt to at most 25 whitespace-delimited words while "
                        "retaining the subject, procedural verb, and AF/ColabFold name when it proves execution."
                    )
                if any("ran_alphafold lacks" in error for error in validation_errors):
                    repair_parts.append(
                        "For ran_alphafold, quote a complete short procedural clause that includes the "
                        "attributable subject or passive construction, the run/prediction verb, and the "
                        "AlphaFold model/server. Remove the action only when no such source clause exists; "
                        "then preserve supported integration and flag prediction_origin_unclear."
                    )
                if any("ran_colabfold lacks" in error for error in validation_errors):
                    repair_parts.append(
                        "For ran_colabfold, quote a complete short procedural clause containing the subject "
                        "or passive construction, an execution/modeling verb, and ColabFold or colabfold_batch. "
                        "Do not submit a clipped fragment or infer execution from a pre-existing model."
                    )
                if any("docking_or_screening requires" in error for error in validation_errors):
                    repair_parts.append(
                        "If genuine molecular, ligand, or protein-interaction docking is present, retain "
                        "docking_or_screening only when its action_evidence links one or more quotes that "
                        "together explicitly show both the AF prediction and the molecular docking. Remove "
                        "the action when the evidence only describes fitting into cryo-EM/electron density."
                    )
                if any("explicit evaluation of this study's AF predictions" in error for error in validation_errors):
                    repair_parts.append(
                        "Add benchmarked_or_evaluated with an exact short evidence quote when the study "
                        "analyzes AF accuracy, pLDDT, PAE, confidence, failures, or model limitations. "
                        "Do not upgrade a target-specific evaluation to R4 solely for this reason."
                    )
                repair_parts.append(
                    "Return exactly one complete JSON object. Errors: "
                    + json.dumps(validation_errors[:12], ensure_ascii=False)
                )
                # Empty content is common when a thinking response spends its entire
                # output budget on reasoning. Do not add a meaningless assistant turn.
                if raw_text.strip():
                    messages.append({"role": "assistant", "content": raw_text})
                messages.append({"role": "user", "content": " ".join(repair_parts)})
        return clean_log_value({
            **envelope(), "ok": False, "error": "Model response failed validation",
            "validation_errors": validation_errors[:20], "response_excerpt": raw_text[:2000],
        }, api_key)
    except Exception as exc:
        return clean_log_value({**envelope(), "ok": False, "error": str(exc)[:2000]}, api_key)


def validate_args(args: argparse.Namespace) -> None:
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    if args.pending_limit is not None and args.pending_limit <= 0:
        raise ValueError("--pending-limit must be positive")
    if args.pending_limit is not None and not args.all:
        raise ValueError("--pending-limit requires --all")
    for name in ("max_api_calls", "workers", "max_output_tokens"):
        if getattr(args, name) <= 0:
            raise ValueError(f"--{name.replace('_', '-')} must be positive")
    if args.http_retries < 0 or args.validation_retries < 0:
        raise ValueError("Retry counts cannot be negative")
    parsed = urlsplit(args.endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("--endpoint must be a full HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("--endpoint must not contain credentials, query parameters, or fragments")
    args.provider_family = model_family(args.model)
    args.resolved_api_style = resolve_api_style(args.endpoint, args.api_style)
    endpoint_path = parsed.path.rstrip("/").casefold()
    if args.resolved_api_style == "responses" and not endpoint_path.endswith("/responses"):
        raise ValueError("Responses API style requires an endpoint ending in /responses")
    if args.resolved_api_style == "chat_completions" and not endpoint_path.endswith("/chat/completions"):
        raise ValueError("Chat Completions style requires an endpoint ending in /chat/completions")
    if args.temperature is not None and not 0 <= args.temperature <= 2:
        raise ValueError("--temperature must be between 0 and 2")
    if args.top_p is not None and not 0 < args.top_p <= 1:
        raise ValueError("--top-p must be greater than 0 and at most 1")

    thinking = effective_thinking(args)
    if args.provider_family == "deepseek":
        if args.resolved_api_style != "chat_completions":
            raise ValueError("This audited DeepSeek profile currently requires Chat Completions")
        if thinking != "enabled":
            raise ValueError("DeepSeek V4 high-reasoning runs require --thinking enabled (or auto)")
        if args.reasoning_effort not in {"low", "high", "max"}:
            raise ValueError("DeepSeek V4 requires explicit --reasoning-effort low, high, or max")
        if args.temperature is not None or args.top_p is not None:
            raise ValueError("DeepSeek thinking mode ignores temperature/top-p; omit both for an auditable run")
    elif args.provider_family == "glm":
        if args.resolved_api_style != "chat_completions":
            raise ValueError("The GLM-5.3-Flash profile requires Chat Completions")
        if thinking != "enabled":
            raise ValueError("GLM-5.3-Flash only supports --thinking enabled (or auto)")
        if args.reasoning_effort not in {"low", "high", "max"}:
            raise ValueError("GLM-5.3-Flash requires explicit --reasoning-effort low, high, or max")
        if args.temperature is None:
            args.temperature = 1.0
        if args.top_p is None:
            args.top_p = 0.95
        if args.temperature > 1:
            raise ValueError("GLM-5.3-Flash temperature must not exceed 1")
    elif args.provider_family == "openai" and model_slug_name(args.model).startswith("gpt-5.6"):
        if args.resolved_api_style != "responses":
            raise ValueError("GPT-5.6 audited reasoning runs require --api-style responses")
        if args.reasoning_effort not in REASONING_EFFORTS:
            raise ValueError("GPT-5.6 requires an explicit --reasoning-effort")
        if args.response_format != "json_schema":
            raise ValueError("GPT-5.6 Responses runs require --response-format json_schema")
        if thinking not in {"none"}:
            raise ValueError("GPT-5.6 uses reasoning.effort; omit the provider-specific thinking toggle")
        if args.temperature is not None or args.top_p is not None:
            raise ValueError("Omit temperature/top-p for the audited GPT-5.6 reasoning profile")
    args.effective_thinking = thinking


def select_scope(packets: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    ids = [p.get("work_id") for p in packets]
    reviews = [p.get("review_id") for p in packets]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("Input packets contain missing/duplicate work_id values")
    if not all(reviews) or len(reviews) != len(set(reviews)):
        raise ValueError("Input packets contain missing/duplicate review_id values")
    requested = args.work_id
    if len(requested) != len(set(requested)):
        raise ValueError("--work-id contains duplicate IDs")
    unknown = set(requested) - set(ids)
    if unknown:
        raise ValueError(f"Requested work IDs absent from input: {sorted(unknown)}")
    scoped = [p for p in packets if not requested or p["work_id"] in requested]
    # Freeze identity BEFORE checking model eligibility or completed outputs.
    return scoped if args.all else scoped[:args.limit]


def completed_records(
    paths: list[Path], packets: list[dict[str, Any]], signature: dict[str, Any]
) -> set[str]:
    current = {p["work_id"]: p for p in packets}
    completed: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        for record in read_jsonl(path):
            work_id = record.get("work_id")
            if work_id in completed:
                raise ValueError(f"Duplicate completed ID in output/forced-U history: {work_id}")
            if work_id not in current or record.get("input_packet_sha256") != fingerprint(current[work_id]):
                raise ValueError(f"Cannot resume {work_id}: input fingerprint differs or is absent; use a new output path")
            if record.get("run_signature") != signature:
                raise ValueError(f"Cannot resume {work_id}: model/prompt/schema/settings differ; use a new output path")
            completed.add(work_id)
    return completed


def main() -> int:
    args = parse_args()
    validate_args(args)
    prompt_bytes = args.prompt.read_bytes()
    schema_bytes = args.schema.read_bytes()
    prompt = prompt_bytes.decode("utf-8")
    schema = json.loads(schema_bytes.decode("utf-8"))
    if schema.get("properties", {}).get("schema_version", {}).get("const") != "af-model-review-output-v2":
        raise ValueError("This runner requires the v2 review schema; historical v1 artifacts remain unchanged")
    validator = Draft202012Validator(schema)
    validator.check_schema(schema)
    embed_schema = not (
        args.resolved_api_style == "responses" and args.response_format == "json_schema"
    )
    system_message = make_system_message(prompt, schema, embed_schema=embed_schema)
    code_paths = protocol_source_paths()
    dependency_lock = PROJECT_ROOT / "uv.lock"
    signature = {
        "provider": args.provider, "model": args.model, "endpoint": args.endpoint,
        "prompt_sha256": sha256_bytes(prompt_bytes),
        "schema_sha256": sha256_bytes(schema_bytes),
        "protocol_code_sha256": protocol_code_sha256(code_paths),
        "dependency_lock_sha256": (
            sha256_bytes(dependency_lock.read_bytes()) if dependency_lock.is_file() else None
        ),
        "api_style": args.resolved_api_style,
        "provider_family": args.provider_family,
        "thinking": args.effective_thinking,
        "thinking_history": "clear",
        "reasoning_effort": args.reasoning_effort,
        "response_format": args.response_format,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_output_tokens": args.max_output_tokens,
        "timeout_seconds": args.timeout,
        "http_retries": args.http_retries,
        "validation_retries": args.validation_retries,
        "router_metadata_requested": args.provider.casefold() == "openrouter",
    }

    packets = [prepare_packet(packet) for packet in read_jsonl(args.input)]
    scope = select_scope(packets, args)
    errors_path = args.errors or args.output.with_name(args.output.stem + ".errors.jsonl")
    attempts_path = args.attempts or args.output.with_name(args.output.stem + ".attempts.jsonl")
    forced_path = args.output.with_name(args.output.stem + ".forced_u.jsonl")
    paths = [args.output, errors_path, attempts_path, forced_path]
    resolved = [p.resolve() for p in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("Output, errors, attempts, and forced-U paths must be distinct")
    if set(resolved) & {args.input.resolve(), args.prompt.resolve(), args.schema.resolve()}:
        raise ValueError("Output files cannot overwrite input/prompt/schema files")
    if any(path.exists() for path in paths) and not (args.resume or args.force or args.dry_run):
        raise FileExistsError("Output or sidecar exists; choose a new output path, or explicitly --resume/--force")
    completed = completed_records([args.output, forced_path], packets, signature) if args.resume else set()
    pending = [p for p in scope if p["work_id"] not in completed]
    selected = [p for p in pending if p["model_eligible"]]
    if args.pending_limit is not None:
        selected = selected[: args.pending_limit]
    forced = [p for p in pending if not p["model_eligible"]]
    estimated_tokens = sum(p.get("estimated_input_tokens", 0) for p in selected)

    print(f"Input records:          {len(packets):,}")
    print(f"Fixed scope records:    {len(scope):,}")
    print(f"Model-eligible in scope:{sum(p['model_eligible'] for p in scope):,}")
    print(f"Already completed:      {sum(p['work_id'] in completed for p in scope):,}")
    print(f"Selected API records:   {len(selected):,}")
    print(f"Forced U, no API:        {len(forced):,}")
    print(f"Estimated packet tokens:{estimated_tokens:,}")
    print(f"Provider/model:         {args.provider} / {args.model}")
    print(f"Endpoint host:          {urlsplit(args.endpoint).netloc}")
    print(f"API style:              {args.resolved_api_style}")
    print(f"Thinking/effort:        {args.effective_thinking} / {args.reasoning_effort or 'provider_default'}")
    print(f"Max output tokens:      {args.max_output_tokens:,}")
    print(f"Hard API-call cap:      {args.max_api_calls:,}")
    print(f"Abstract quality:       {dict(Counter(p['input_quality']['abstract_status'] for p in scope))}")
    if len(scope) <= 200:
        print("Fixed IDs:              " + ", ".join(p["work_id"] for p in scope))
    else:
        preview = ", ".join(p["work_id"] for p in scope[:20])
        print(f"Fixed IDs:              {preview}, ... ({len(scope) - 20:,} more)")
    if args.dry_run:
        print("Dry run: no API calls made and no files written")
        return 0
    if not pending:
        print("Nothing to do; the fixed scope is already completed")
        return 0

    api_key = os.environ.get(args.api_key_env, "")
    if selected and not api_key:
        raise RuntimeError(f"Environment variable is empty or missing: {args.api_key_env}")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if args.force else "a"
    budget = CallBudget(args.max_api_calls)
    run_id = f"{args.provider}-{uuid.uuid4().hex[:12]}"
    artifact_dir, manifest_path, manifest = create_run_artifact(
        args=args,
        run_id=run_id,
        signature=signature,
        scope=scope,
        selected=selected,
        forced=forced,
    )
    try:
        artifact_reference = str(artifact_dir.resolve().relative_to(args.output.parent.resolve()))
    except ValueError:
        artifact_reference = str(artifact_dir.resolve())
    successes = failures = 0
    totals: dict[str, int] = {}
    accounting: dict[str, Any] = {}
    try:
        with (
            args.output.open(mode, encoding="utf-8") as output_handle,
            errors_path.open(mode, encoding="utf-8") as error_handle,
            attempts_path.open(mode, encoding="utf-8") as audit_handle,
            forced_path.open(mode, encoding="utf-8") as forced_handle,
        ):
            audit = AttemptAudit(audit_handle, api_key)
            audit.emit({
                "event": "run_started", "run_id": run_id, "run_signature": signature,
                "run_artifact": artifact_reference,
                "input_file_sha256": sha256_bytes(args.input.read_bytes()),
                "scope_work_ids": [p["work_id"] for p in scope],
                "api_work_ids": [p["work_id"] for p in selected],
                "forced_u_work_ids": [p["work_id"] for p in forced],
                "workers": args.workers, "timeout_seconds": args.timeout,
                "http_retries": args.http_retries, "validation_retries": args.validation_retries,
                "max_api_calls": args.max_api_calls, "pending_limit": args.pending_limit,
            })
            for packet in forced:
                result = {
                    "schema_version": "af-forced-review-output-v2",
                    "run_id": run_id, "completed_at_utc": utc_now(),
                    "provider": args.provider, "model": args.model,
                    "run_artifact": artifact_reference,
                    "run_signature": signature,
                    "work_id": packet["work_id"], "review_id": packet["review_id"],
                    "input_packet_sha256": fingerprint(packet),
                    "evidence_tier": packet["evidence_tier"],
                    "input_quality": packet["input_quality"],
                    "api_calls": 0, "response": packet["forced_decision"],
                }
                forced_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                forced_handle.flush()
                audit.emit({"event": "forced_u", **result})

            def worker(packet: dict[str, Any]) -> dict[str, Any]:
                return review_one(
                    packet=packet, args=args, api_key=api_key, system_message=system_message,
                    schema=schema, validator=validator, budget=budget, run_id=run_id,
                    audit=audit, signature=signature, artifact_reference=artifact_reference,
                )

            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(worker, packet) for packet in selected]
                for future in tqdm(
                    as_completed(futures), total=len(futures), desc="Model review", unit="work"
                ):
                    result = future.result()
                    if result.get("ok") is False:
                        error_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                        error_handle.flush()
                        failures += 1
                    else:
                        output_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                        output_handle.flush()
                        successes += 1
            totals, accounting = aggregate_usage(audit.finished)
            audit.emit({
                "event": "run_finished", "run_id": run_id,
                "run_artifact": artifact_reference,
                "validated": successes, "failed": failures, "forced_u": len(forced),
                "api_calls": budget.used, "reported_api_usage": totals,
                "usage_accounting": accounting,
            })
    except BaseException as exc:
        manifest.update({
            "status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
            "completed_at_utc": utc_now(),
            "failure": {
                "type": type(exc).__name__,
                "message": redact_sensitive_text(
                    str(exc).replace(api_key, "[REDACTED]") if api_key else str(exc)
                )[:2000],
            },
        })
        manifest["archived_records"] = archive_run_records(
            artifact_dir=artifact_dir,
            run_id=run_id,
            sources={
                "validated": args.output,
                "errors": errors_path,
                "attempts": attempts_path,
                "forced_u": forced_path,
            },
        )
        write_run_manifest(manifest_path, manifest)
        raise

    response_identities = {
        json.dumps(metadata, ensure_ascii=False, sort_keys=True): metadata
        for attempt in audit.finished
        if (metadata := attempt.get("provider_response_metadata"))
    }
    manifest.update({
        "status": "completed" if failures == 0 else "completed_with_failures",
        "completed_at_utc": utc_now(),
        "outcome": {
            "validated": successes,
            "failed": failures,
            "forced_u": len(forced),
            "api_calls": budget.used,
            "reported_api_usage": totals,
            "usage_accounting": accounting,
        },
        "provider_response_identities": list(response_identities.values()),
    })
    manifest["archived_records"] = archive_run_records(
        artifact_dir=artifact_dir,
        run_id=run_id,
        sources={
            "validated": args.output,
            "errors": errors_path,
            "attempts": attempts_path,
            "forced_u": forced_path,
        },
    )
    write_run_manifest(manifest_path, manifest)

    print(f"Validated outputs:      {successes:,}/{len(selected):,}")
    print(f"Forced U recorded:      {len(forced):,}")
    print(f"Failed outputs:         {failures:,}")
    print(f"API calls used:         {budget.used:,}/{budget.maximum:,}")
    print(f"Reported token totals:  {totals}")
    print(f"Usage reporting complete: {accounting['reporting_complete']}")
    print(f"Output:                 {args.output}")
    print(f"Attempt audit:          {attempts_path}")
    print(f"Forced-U records:       {forced_path}")
    print(f"Run artifact:           {manifest_path}")
    if failures:
        print(f"Errors:                 {errors_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
