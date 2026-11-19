"""User-run combined local activity preparation, descriptive RR and export checks."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import fcntl
import shutil
import tempfile
from pathlib import Path
from common import MODULE, assert_unchanged, connect, environment, literal, output_dir, utc, write_json
from baseline_features import fingerprint
from activity_patterns import (CODE, CONFIG, GUIDE, EXPORTS, attach_sources, build_tables,
                               check_tables, load_inputs, markdown, summary)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study-dir', type=Path, default=MODULE / 'study_events_v1')
    p.add_argument('--leadership-dir', type=Path, default=MODULE / 'leadership_audit_v1')
    p.add_argument('--rr-dir', type=Path, default=MODULE / 'leadership_rr_v1')
    p.add_argument('--layer-dir', type=Path, default=MODULE / 'action_layer_v1')
    p.add_argument('--output-dir', type=Path, default=MODULE / 'activity_patterns_v1')
    p.add_argument('--threads', type=int, default=2)
    p.add_argument('--memory-gib', type=int, default=4)
    p.add_argument('--dry-run', action='store_true')
    return p


def publish(args, c, inv, dirs, dest):
    if shutil.disk_usage(dest.parent).free < c['minimum_free_disk_gib'] * 1024**3:
        raise ValueError('At least 4 GiB free required')
    stage = Path(tempfile.mkdtemp(prefix='.activity-patterns-incomplete-', dir=dest.parent))
    print('Staging (retained on failure): ' + str(stage), flush=True)
    con = connect(args.threads, args.memory_gib, spill=stage / '.spill')
    try:
        attach_sources(con, dirs)
        build_tables(con, dirs, c)
        checks = check_tables(con)
        if any(checks.values()):
            raise ValueError('Source / denominator checks failed: ' + str(checks))
        outputs = {}
        for name, order in EXPORTS.items():
            rows = int(con.execute('SELECT count(*) FROM ' + name).fetchone()[0])
            if rows > c['maximum_export_rows']:
                raise ValueError('Export cap exceeded; no truncation: ' + name)
            p = stage / (name + '.parquet')
            con.execute(f'COPY (SELECT * FROM {name} ORDER BY {order}) TO {literal(p)} (FORMAT PARQUET, COMPRESSION ZSTD)')
            fp = fingerprint(p)
            outputs[p.name] = {k: fp[k] for k in ('sha256', 'size_bytes')} | {'rows': rows}
        s = summary(con)
        write_json(stage / 'activity_summary.json', s)
        with (stage / 'activity_report_zh.md').open('x', encoding='utf-8') as stream:
            stream.write(markdown(s))
        write_json(stage / 'validation_report.json', {
            'schema_version': 'nhb-activity-patterns-validation-v1', 'checks': checks,
            'blockers': [], 'activity_descriptives_ready': True, 'descriptive_activity_rr_ready': True,
            'formal_models_ready': False, 'independent_human_gold_standard': False,
            'export_reconstruction_required': True})
        for name in ('activity_summary.json', 'activity_report_zh.md', 'validation_report.json'):
            fp = fingerprint(stage / name)
            outputs[name] = {k: fp[k] for k in ('sha256', 'size_bytes')}
        archive = stage / 'code_and_policy'
        archive.mkdir()
        snapshots = {}
        pinned = {r['path']: r['sha256'] for r in inv}
        for name in CODE + (CONFIG.name, GUIDE.name):
            p = archive / name
            shutil.copyfile(MODULE / name, p)
            fp = fingerprint(p)
            if fp['sha256'] != pinned[str(MODULE / name)]:
                raise ValueError('Implementation changed during execution')
            snapshots['code_and_policy/' + name] = {k: fp[k] for k in ('sha256', 'size_bytes')}
        assert_unchanged(inv)
        write_json(stage / 'activity_manifest.json', {
            'schema_version': 'nhb-activity-patterns-run-v1', 'created_at_utc': utc(),
            'directories': {k: str(v) for k, v in dirs.items()}, 'config': c, 'inputs': inv,
            'outputs': outputs, 'snapshots': snapshots, 'checks': checks, 'environment': environment(),
            'execution': {'threads': args.threads, 'memory_gib': args.memory_gib},
            'provider_requests': 0, 'original_final_database_modified': False,
            'formal_models_ready': False, 'independent_human_gold_standard': False,
            'inference': 'descriptive_only_no_CI_no_p_values_no_causal_effect',
            'raw_document_extraction_repeated': False,
            'complete_version_deduplication_claimed': False})
        con.close(); con = None
        # Reopen exported Parquets and reconstruct from the same pinned inputs before publishing.
        from verify_activity_patterns import verify
        verify(stage, args.threads, args.memory_gib)
        if dest.exists() or dest.is_symlink():
            raise FileExistsError('Destination exists; no overwrite')
        stage.rename(dest)
        print('Combined activity preparation / export reconstruction: PASS')
        print('Confirmed AF studies: ' + str(s['confirmed_AF_main_studies']))
        print('Overlay representatives: ' + str(s['overlay_selected_representatives']) +
              ' / queue ' + str(s['overlay_queue_works']))
        print('Descriptive tables: ' + str(len(EXPORTS)) + '; formal models NOT run')
        print('Saved: ' + str(dest) + '; NEXT verify_activity_patterns.py')
    except BaseException:
        print('INCOMPLETE retained: ' + str(stage) + '; no source/final modifications')
        raise
    finally:
        if con is not None:
            con.close()
    return 0


def main(argv=None):
    p = parser(); args = p.parse_args(argv)
    if not 1 <= args.threads <= 16 or not 1 <= args.memory_gib <= 32:
        p.error('threads 1..16; memory-gib 1..32')
    dirs = {'study': args.study_dir, 'leadership': args.leadership_dir,
            'rr': args.rr_dir, 'layer': args.layer_dir}
    print('Checking frozen action layer, study representatives and leadership-credit chain...', flush=True)
    c, inv, dirs = load_inputs(dirs)
    dest = output_dir(args.output_dir)
    if not dest.parent.is_dir() or any(dest.resolve().is_relative_to(d.resolve()) for d in dirs.values()):
        raise ValueError('Output must be outside frozen inputs with existing parent')
    if args.dry_run:
        print('Dry run: selected hashes, schemas and action reconstruction passed; no files or requests')
        print('Activity aggregation / RR / export counts NOT computed; no keys or LLM calls')
        return 0
    with (MODULE / '.activity-patterns-v1.writer.lock').open('a', encoding='ascii') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another activity writer is running') from exc
        try:
            return publish(args, c, inv, dirs, dest)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


if __name__ == '__main__':
    raise SystemExit(main())
