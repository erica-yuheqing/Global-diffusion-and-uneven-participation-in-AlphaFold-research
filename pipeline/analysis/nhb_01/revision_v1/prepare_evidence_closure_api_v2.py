"""Offline, versioned repair of bibliography provenance and section filtering.

No requests, keys, semantic decisions, resume credit, or old-output edits.
References establish bibliographic identity only, never execution/use evidence.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile

import evidence_closure_api_v1 as old
from fetch_public_evidence import inventory
from local_recall import MODULE, destination, pin, require, sha, write_json
from prepare_evidence_closure_api_v1 import write_jsonl

OUT = MODULE / 'evidence_closure_api_inputs_v2'
DOIS = {
    '10.1038/s41586-019-1923-7': 'AF1',
    '10.1038/s41586-021-03819-2': 'AF2',
    '10.1038/s41586-024-07487-w': 'AF3',
    '10.1101/2021.10.04.463034': 'AlphaFold-Multimer',
}
DOI = re.compile('|'.join(re.escape(d) for d in DOIS), re.I)
DB_TITLE = re.compile(r'AlphaFold\s+Protein\s+Structure\s+Database|'
                      r'massively\s+expanding\s+the\s+structural\s+coverage\s+of\s+protein[\s-]+sequence\s+space', re.I)
ADMIN = re.compile(r'^(?:references?\b|bibliography\b|acknowledg\w*\b|funding\b|footnotes?\b|'
                   r'author\w* contributions?\b|credit\b|declaration\w*\b|conflict\w*\b|'
                   r'competing interests?\b|data availability\b|code availability\b|'
                   r'supplementary\b|electronic supplementary\b|associated data\b|'
                   r'contributor information\b|publisher.?s note\b|peer review\b|source data\b)', re.I)


def heading(name):
    return re.sub(r'^\s*(?:\d+(?:\.\d+)*[.)]?\s+)', '', name or '').strip()


def reference_candidates(doc, path):
    refs, provenance = [], []
    for i, section in enumerate(doc.get('sections', [])):
        if not re.match(r'^(references?\b|bibliography\b)', heading(section.get('title')), re.I):
            continue
        text = section.get('text') or ''
        matches = [(m, DOIS[m.group().lower()]) for m in DOI.finditer(text)]
        matches += [(m, 'AlphaFold-DB-title') for m in DB_TITLE.finditer(text)]
        for match, target in sorted(matches, key=lambda x: x[0].start()):
            # Exact source offsets and verbatim bounded context; no invented
            # reference assembled from OpenAlex citation-graph edges.
            start, end = max(0, match.start()-240), min(len(text), match.end()+160)
            excerpt = text[start:end]
            refs.append({'reference_text': excerpt, 'matched_target': target,
                         'matched_literal': match.group(),
                         'evidence_role': 'bibliographic_identity_only',
                         'limitation': 'Bounded bibliography excerpt may include adjacent entries; in-text citation linkage and actual use are NOT established.'})
            provenance.append({'reference_index': len(refs)-1, 'source_path': str(path),
                               'source_sha256': sha(path), 'source_section_index': i,
                               'start_character': start, 'end_character': end,
                               'matched_start_character': match.start(), 'matched_end_character': match.end(),
                               'text_sha256': hashlib.sha256(excerpt.encode()).hexdigest()})
    return refs, provenance


def repair_packet(row):
    packet, private = old.build_packet(row)
    packet = copy.deepcopy(packet)
    material = packet['input_material']
    removed, blocks, maps = [], [], []
    for block, source in zip(material['evidence_blocks'], private['body_source_map']):
        if ADMIN.match(heading(block['section'])) or heading(block['section']).lower() in {'title', 'abstract'}:
            removed.append(source)
            continue
        block['index'] = len(blocks)
        source['block_index'] = len(blocks)
        blocks.append(block); maps.append(source)
    material['evidence_blocks'] = blocks
    refs, ref_map = [], []
    if row['body_document_path']:
        path = Path(row['body_document_path'])
        require(sha(path) == row['body_document_sha256'], 'Body changed during reference repair')
        refs, ref_map = reference_candidates(json.loads(path.read_text()), path)
    material['matched_seed_references'] = refs
    packet['context_policy'] = {
        'version': 'figure1-closure-scientific-sections-bibliography-v2',
        'full_document_included': False,
        'section_filter': 'normalized explicit heading exclusion; not a guarantee against inline administrative text',
        'matched_references': 'literal known AF DOI/title in source bibliography; identity only, not scientific use',
        'limitations': 'Extracted body may omit equations, tables, supplements and citation identifiers; bibliography context does not resolve in-text citation linkage.',
    }
    # Recalculate from the repaired complete packet; no inherited oversize
    # exemption/forced route is allowed to mask the new token estimate.
    packet.pop('production_protocol', None)
    packet['evidence_tier'] = 'fulltext_evidence' if blocks else 'abstract_only'
    packet['forced_decision'] = None
    packet['input_quality']['flags'] = [x for x in packet['input_quality']['flags'] if x != 'oversize_context_requires_human_review']
    packet = old.prepare_packet(packet)
    if packet['model_eligible'] and packet['estimated_input_tokens'] > old.CAP:
        packet.update(production_protocol='figure1-closure-api-v2', evidence_tier='oversize_context_human_review',
                      model_eligible=False, forced_decision={'label':'U', 'reason':'Complete repaired packet exceeds 30,000 estimated tokens; manual evidence review, not non-use.'})
        packet = old.prepare_packet(packet)
    private.update(body_source_map=maps, additionally_excluded_sections=removed,
                   reference_source_map=ref_map, input_packet_sha256=old.fingerprint(packet),
                   old_v1_packet_sha256=old.fingerprint(old.build_packet(row)[0]))
    require(old.prepare_packet(packet) == packet, 'Repaired packet not idempotent')
    return packet, private


def assemble():
    old.verify_inputs()
    rows = json.loads((old.SOURCE/'packets_private.json').read_text())
    pairs = [repair_packet(row) for row in rows]
    packets, private = [p[0] for p in pairs], [p[1] for p in pairs]
    ids = json.loads((old.INPUTS/'smoke20_ids.json').read_text())
    summary = {'queue_works':len(packets), 'api_eligible':sum(p['model_eligible'] for p in packets),
               'tiers':dict(Counter(p['evidence_tier'] for p in packets)),
               'works_with_restored_AF_bibliography':sum(bool(p['input_material']['matched_seed_references']) for p in packets),
               'restored_reference_excerpts':sum(len(p['input_material']['matched_seed_references']) for p in packets),
               'additional_admin_sections_excluded':sum(len(p['additionally_excluded_sections']) for p in private),
               'estimated_tokens_per_model':sum(p['estimated_input_tokens'] for p in packets if p['model_eligible']),
               'old_API_outputs_are_not_v2_resume_credit':True,
               'paid_calls':0, 'public_requests':0, 'semantic_decisions':0,
               'full_queue_ready':False, 'next_gate':'semantic review and scope decision; no API runner dispatched'}
    return packets, private, ids, summary


def verify(directory=OUT):
    manifest = json.loads((directory/'run_manifest.json').read_text())
    require(inventory(directory) == manifest['outputs'], 'v2 frozen inventory differs')
    for p in manifest['inputs']:
        require(sha(p['path']) == p['sha256'], 'v2 pinned source/code differs')
    packets, private, ids, summary = assemble()
    require(old.read_jsonl(directory/'closure586_model_inputs.jsonl') == packets, 'v2 full reconstruction differs')
    require(json.loads((directory/'provenance_private.json').read_text()) == private, 'v2 provenance differs')
    require(json.loads((directory/'summary.json').read_text()) == summary, 'v2 summary differs')
    by_id = {p['work_id']:p for p in packets}
    require(old.read_jsonl(directory/'smoke20_model_inputs.jsonl') == [by_id[w] for w in ids], 'v2 smoke differs')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true'); parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        print('Offline v2 reconstruction: PASS;', json.dumps(verify(), ensure_ascii=False)); return
    packets, private, ids, summary = assemble()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.dry_run:
        print('No files, requests, keys, decisions or resume credit'); return
    out = destination(OUT)
    stage = Path(tempfile.mkdtemp(prefix='.closure-api-v2-', dir=MODULE)); stage.chmod(0o700)
    write_jsonl(stage/'closure586_model_inputs.jsonl', packets)
    by_id = {p['work_id']:p for p in packets}
    write_jsonl(stage/'smoke20_model_inputs.jsonl', [by_id[w] for w in ids])
    write_json(stage/'provenance_private.json', private); write_json(stage/'summary.json', summary)
    sources = [old.INPUTS/'run_manifest.json', old.SOURCE/'packets_private.json', Path(__file__), Path(old.__file__)]
    write_json(stage/'run_manifest.json', {'schema':'figure1-closure-api-input-freeze-v2',
                'inputs':[pin(p) for p in sources], 'summary':summary, 'outputs':inventory(stage)})
    verify(stage); stage.rename(out)
    print('New input version exported + reconstructed: PASS;', out, '; no API dispatched')


if __name__ == '__main__': main()
