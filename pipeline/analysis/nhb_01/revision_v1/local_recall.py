"""Offline candidate recall audit. Does not assign AF labels or modify upstream data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone

import duckdb
import pyarrow.parquet as pq

MODULE = Path(__file__).resolve().parent
ROOT = MODULE.parents[2]
MASTER = ROOT / 'analysis/final_v1/out/works_analysis_master.parquet'
REFS = ROOT / 'derived_tables/work_references'
DATABASE = ROOT / 'fulltext/manifest/fulltext_manifest.sqlite'
SEEDS = ROOT / 'config/alphafold_seed_works.json'
PLAN = Path('/historical-workspace/Library/Mobile Documents/iCloud~md~obsidian/Documents/Jaden/01_Projects/IGN/Revision/figure1-revision-plan.md')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def regular(path, root):
    path, root = Path(path).absolute(), Path(root).resolve()
    require(not path.is_symlink() and path.is_file(), 'Input must be a regular non-symlink file')
    require(path.resolve().is_relative_to(root), 'Input outside approved root')
    require(all(not p.is_symlink() for p in path.parents if p.is_relative_to(root)), 'Symlink ancestor')
    require(path.stat().st_nlink == 1, 'Multiply linked input')
    return path


def sql_path(path):
    return "'" + str(path).replace("'", "''") + "'"


def pin(path, root=ROOT):
    path = regular(path, root)
    result = {'path': str(path), 'sha256': sha(path), 'size_bytes': path.stat().st_size}
    if path.suffix == '.parquet':
        result.update(rows=pq.ParquetFile(path).metadata.num_rows,
                      schema=str(pq.read_schema(path)))
    return result


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    Path(path).chmod(0o600)


def write_csv(path, rows, fields):
    with Path(path).open('x', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    Path(path).chmod(0o600)


def destination(path):
    path = Path(path).absolute()
    require(not path.exists() and not path.is_symlink(), 'Output exists; choose a new version')
    require(path.parent.resolve().is_relative_to(MODULE), 'Output must be within revision_v1')
    return path


def prepare_views(c, master, references, seed_config, protocol):
    schema = set(pq.read_schema(master).names)
    columns = ['work_id', 'doi', 'title', 'abstract', 'publication_year', 'publication_date',
               'work_type', 'candidate_reviewed', 'af_use_label', 'adoption_eligible',
               'primary_subfield_id', 'primary_subfield_display_name']
    require(set(columns) <= schema, 'Master schema does not meet explicit contract')
    c.execute(f"CREATE VIEW master AS SELECT {','.join(columns)} FROM read_parquet({sql_path(master)})")
    af1 = c.execute("SELECT DISTINCT work_id FROM master WHERE lower(regexp_replace(doi,'^https?://(dx\\.)?doi.org/',''))=?",
                    [protocol['af1_doi']]).fetchall()
    require(len(af1) == 1, 'AF1 DOI must resolve to exactly one local work; manual identity review needed')
    seeds = [(str(s['openalex_id']).rsplit('/', 1)[-1].upper(), False) for s in seed_config['seeds']]
    af1_id = af1[0][0].rsplit('/', 1)[-1].upper()
    require(af1_id not in [x[0] for x in seeds], 'AF1 already present; this recovery rationale must be revised')
    seeds.append((af1_id, True))
    require(len(set(x[0] for x in seeds)) == len(seeds), 'Duplicate seed identities')
    c.execute('CREATE TEMP TABLE seeds(work_id VARCHAR,is_af1 BOOLEAN)')
    c.executemany('INSERT INTO seeds VALUES (?,?)', seeds)
    for path in references:
        require(set(pq.read_schema(path).names) >= {'source_work_id','referenced_work_id'}, 'Reference schema mismatch')
    paths = '[' + ','.join(sql_path(p) for p in references) + ']'
    c.execute(f'''CREATE TEMP TABLE hits AS
        SELECT regexp_extract(upper(r.source_work_id),'W[0-9]+$',0) AS work_id,
          bool_or(s.is_af1) AS cites_af1, bool_or(NOT s.is_af1) AS cites_existing_seed
        FROM read_parquet({paths}) r JOIN seeds s
          ON regexp_extract(upper(r.referenced_work_id),'W[0-9]+$',0)=s.work_id
        GROUP BY 1''')
    c.execute('''CREATE TEMP TABLE queue AS
        SELECT m.*,coalesce(h.cites_af1,false) AS cites_af1,
          coalesce(h.cites_existing_seed,false) AS cites_existing_seed,
          regexp_matches(lower(coalesce(m.title,'')||' '||coalesce(m.abstract,'')),?) AS keyword_hit,
          m.work_id IN (SELECT work_id FROM seeds) AS seed_self,
          m.work_type IN ('article','review','preprint') AS document_eligible
        FROM master m LEFT JOIN hits h USING(work_id)
        WHERE m.publication_year BETWEEN 2015 AND 2025 AND NOT m.candidate_reviewed
          AND (h.work_id IS NOT NULL OR m.work_id IN (SELECT work_id FROM seeds)
             OR regexp_matches(lower(coalesce(m.title,'')||' '||coalesce(m.abstract,'')),?))''',
        [protocol['keyword_regex'], protocol['keyword_regex']])
    require(c.execute('SELECT count(*)-count(DISTINCT work_id) FROM queue').fetchone()[0] == 0, 'Duplicate queued works')
    return af1_id


def evidence_rows(c, database):
    rows = c.execute('SELECT * FROM queue ORDER BY publication_year,work_id').df().to_dict('records')
    require(len(rows) <= 100000, 'Review queue exceeds bounded limit; stop for scope review')
    db = sqlite3.connect(f'file:{database}?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
    result = []
    try:
        for row in rows:
            record = db.execute('''SELECT abstract,abstract_source,parse_status,parsed_document_path,context_count
                FROM works WHERE work_id=?''', [row['work_id']]).fetchone()
            manifest_abstract = record[0] if record else None
            abstract = row['abstract'] if row['abstract'] and row['abstract'].strip() else manifest_abstract
            document = record[3] if record else None
            doc_exists = False
            if document:
                p = Path(document)
                doc_exists = p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(ROOT)
            row.update(abstract=abstract, abstract_present=bool(abstract and abstract.strip()),
                       abstract_source='frozen_master' if row['abstract'] and row['abstract'].strip()
                       else (record[1] if record and manifest_abstract else 'missing'),
                       manifest_record_present=record is not None,
                       parsed_fulltext_present=bool(record and record[2]=='success' and doc_exists),
                       context_count=int(record[4] or 0) if record else 0,
                       parsed_document_path=document if doc_exists else '',
                       review_status='pending_evidence_review',af_use_label='',adoption_eligible='')
            row['evidence_route'] = ('local_parsed_fulltext' if row['parsed_fulltext_present'] else
                                     'abstract_present_quality_pending' if row['abstract_present'] else
                                     'metadata_only_needs_evidence')
            result.append(row)
    finally:
        db.rollback(); db.close()
    return result


def summarize(c, rows):
    from collections import Counter
    eligible = [r for r in rows if r['document_eligible']]
    return {'scope':'all local 2015–2025 master works; article/review/preprint separate from other types',
            'new_candidates_all_types':len(rows),'new_candidates_eligible':len(eligible),
            'by_year_eligible':dict(sorted(Counter(str(r['publication_year']) for r in eligible).items())),
            'evidence_routes_eligible':dict(Counter(r['evidence_route'] for r in eligible)),
            'overlapping_signals_eligible':{k:sum(bool(r[k]) for r in eligible)
                for k in ('cites_af1','cites_existing_seed','keyword_hit','seed_self')},
            'year2020_eligible':sum(r['publication_year']==2020 for r in eligible),
            'old_confirmed_2020':c.execute("SELECT count(*) FROM master WHERE publication_year=2020 AND af_use_label='yes' AND adoption_eligible='yes' AND work_type IN ('article','review','preprint')").fetchone()[0],
            'af_labels_changed':0,'api_calls':0,'llm_calls':0,
            'ready_for_recall_review':True,'ready_for_final_revised_figure':False,
            'limitations':['Citations/keywords are recall signals, not established use.',
              'Reference lists may belong to later preprint revisions; publication dates are not usage dates.',
              'Local field corpus coverage is not global complete coverage.',
              'New version links and evidence quality remain to be reviewed.']}


def report(path, summary):
    years = '\n'.join(f'| {y} | {n:,} |' for y,n in summary['by_year_eligible'].items())
    routes = '\n'.join(f'- `{k}`：{n:,}篇。' for k,n in summary['evidence_routes_eligible'].items())
    text = f'''# Figure 1 新版：候选召回补查结果

本轮为离线召回核查，非新增AF使用结论，非独立人工金标准。保留原冻结数据，未读取外置原始JSONL，未调用API或LLM。

## 数量

全类型新增候选：{summary['new_candidates_all_types']:,}篇；article／review／preprint新增候选：{summary['new_candidates_eligible']:,}篇。其中2020年{summary['year2020_eligible']:,}篇，旧版确认使用仍为{summary['old_confirmed_2020']}篇，不能直接相加。

| 年份 | 新增适格候选 |
| --- | ---: |
{years}

## 证据可用性

{routes}

摘要非空不等于摘要质量合格；本轮只审计可用性。正文只检查manifest的成功解析状态和文件存在性，未解析正文内容。缺证据不能自动标成no，关键词或引用也不能自动标成yes。

## 输出导航

- [汇总JSON](summary.json)
- [新增候选操作清单（限制本地使用）](candidate_review_private.csv)：含work_id／DOI／标题／摘要，权限0600，控制台及公开汇总不打印原始行。
- [逐年召回及来源计数](recall_counts_by_year.csv)
- [受影响分析及推进门槛](affected_outputs_zh.md)
- [冻结月份规则](protocol.json)
- [源数据／代码哈希](run_manifest.json)

## 口径

2020.01–2021.06为Pre-AF2 release；2021.07–2024.04为AF2 era；2024.05–2025.12为AF3 era。2020不单列过渡期。时期按发表月份，不按模型版本。新增候选进入批准的审阅层后须移出筛查阴性，使用标签必须另行批准；不能只更改AF分子而保留旧比较组。

## 下一步

优先检查2015–2019首次观察历史及2020–2021早期候选；其他年份使用同一规则。先形成证据质量核查／定向补取范围，再确认是否需要付费模型调用。全部新标签／版本链接批准后，才能发布正式新版a–d、更新Methods／Results及阅读包。本目录不替代旧最终数据库。

## 软件与流程参考

exploratory-data-analysis影响了离线、分层、缺失保留与来源锁；scientific-visualization影响了新版面板与发布门槛。作者仍需进行语义及视觉核查。

Kassis T, Agarwal V, He Y, Patel D, Brueckner AM. Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents (2026). [doi:10.48550/arXiv.2609.00065](https://doi.org/10.48550/arXiv.2609.00065).
'''
    path.write_text(text, encoding='utf-8'); path.chmod(0o600)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,default=MODULE/'recall_audit_v1')
    p.add_argument('--threads',type=int,default=2)
    p.add_argument('--memory-gib',type=int,default=2)
    p.add_argument('--dry-run',action='store_true')
    a=p.parse_args(argv)
    require(1<=a.threads<=4 and 1<=a.memory_gib<=4,'Threads 1–4; memory 1–4 GiB')
    dest=destination(a.output_dir)
    refs=sorted(REFS.glob('*.parquet'))
    require(0<len(refs)<=100,'Unexpected reference shard scope')
    for f in [MASTER,DATABASE,SEEDS,*refs]: regular(f,ROOT)
    require(pq.ParquetFile(MASTER).metadata.num_rows<=7000000,'Master row cap exceeded')
    require(sum(pq.ParquetFile(f).metadata.num_rows for f in refs)<=250000000,'Reference row cap exceeded')
    require(sum(f.stat().st_size for f in refs)<=4*1024**3,'Reference byte cap exceeded')
    protocol=json.loads((MODULE/'protocol.json').read_text())
    if a.dry_run:
        print('Local schemas/scope checked; no content scan, writes, network, labels or API keys')
        return 0
    require(shutil.disk_usage(MODULE).free>=3*1024**3,'Insufficient free disk')
    print('Hashing frozen inputs, then scanning all bounded reference shards...',flush=True)
    paths=[MASTER,DATABASE,SEEDS,*refs,MODULE/'protocol.json',Path(__file__)]
    pins=[pin(f) for f in paths]
    plan_root=PLAN.parent
    pins.append(pin(PLAN,plan_root))
    stage=Path(tempfile.mkdtemp(prefix='.recall-incomplete-',dir=MODULE));stage.chmod(0o700)
    c=duckdb.connect(config={'threads':a.threads,'memory_limit':f'{a.memory_gib}GiB',
        'temp_directory':str(stage/'spill'),'max_temp_directory_size':'2GiB',
        'preserve_insertion_order':False,'autoinstall_known_extensions':False,'autoload_known_extensions':False})
    try:
        prepare_views(c,MASTER,refs,json.loads(SEEDS.read_text()),protocol)
        rows=evidence_rows(c,DATABASE); summary=summarize(c,rows)
        fields=list(rows[0]) if rows else ['work_id','review_status']
        write_csv(stage/'candidate_review_private.csv',rows,fields)
        counts=c.execute('''SELECT publication_year,document_eligible,count(*) AS new_candidates,
            sum(cites_af1)::BIGINT AS cites_af1,sum(cites_existing_seed)::BIGINT AS cites_existing_seed,
            sum(keyword_hit)::BIGINT AS keyword_hits,sum(seed_self)::BIGINT AS seed_self
            FROM queue GROUP BY 1,2 ORDER BY 1,2''').df()
        counts.to_csv(stage/'recall_counts_by_year.csv',index=False)
        write_json(stage/'summary.json',summary);write_json(stage/'protocol.json',protocol)
        report(stage/'README_zh.md',summary)
        shutil.copyfile(PLAN,stage/'figure1-revision-plan_source.md')
        shutil.copyfile(MODULE/'affected_outputs_zh.md',stage/'affected_outputs_zh.md')
        c.close();c=None
        for f in pins: require(sha(f['path'])==f['sha256'],'An input changed during the audit')
        shutil.copyfile(Path(__file__),stage/'local_recall_code_snapshot.py')
        outputs={f.name:{'sha256':sha(f),'size_bytes':f.stat().st_size} for f in stage.iterdir() if f.is_file()}
        write_json(stage/'run_manifest.json',{'schema_version':'nhb01-local-recall-v1',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'inputs':pins,'outputs':outputs,
            'versions':{n:importlib.metadata.version(n) for n in ['duckdb','pyarrow','pandas']},
            'summary':summary,'upstream_modified':False,'identifier_exports':'private operational queue only',
            'post_hoc_revision':True,'api_calls':0})
        for f in stage.iterdir():
            if f.is_file(): f.chmod(0o600)
        require(not dest.exists(),'Refusing output replacement');stage.rename(dest)
        print(f"Recall audit complete; new eligible candidates: {summary['new_candidates_eligible']:,}; 2020: {summary['year2020_eligible']:,}")
        print('Labels unchanged; final revised figure blocked until review approval; no API calls')
        return 0
    finally:
        if c is not None:c.close()


if __name__=='__main__':raise SystemExit(main())
