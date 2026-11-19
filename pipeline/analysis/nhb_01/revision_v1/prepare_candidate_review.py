"""Offline evidence screening/version leads; no labels, merges, API or database writes."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

import consolidate_public_evidence as consolidated
from fetch_public_evidence import inventory, norm_doi
from local_recall import MODULE, ROOT, MASTER, regular, require, sha, destination, write_json, write_csv, sql_path

QUALITY_FILE = ROOT/'code/fulltext_pipeline/model_review_support.py'
PROMPT = ROOT/'config/af_review_prompt_v4.txt'
AF = re.compile(r'(?<![A-Za-z0-9])(?:alpha[\s‐‑–—-]*fold(?:[\s-]*[123])?|colab[\s-]*fold|afdb|af[123])(?![A-Za-z0-9])', re.I)
DECISIONS = ('primary_label','relevance_level','evidence_level','af_related_label','af_use_label',
             'adoption_eligible','observed_actions','annotator_id','evidence_quote','reasoning_summary')


def strict_json(path, root=MODULE):
    path=regular(path,root); require(path.stat().st_size<=32*1024**2,'JSON exceeds bounded review input cap')
    def pairs(items):
        out={}
        for key,value in items:
            require(key not in out,'Duplicate JSON key');out[key]=value
        return out
    def nonfinite(value):raise ValueError('Nonfinite JSON rejected')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=nonfinite)


def load_quality():
    spec=importlib.util.spec_from_file_location('revision_existing_quality',regular(QUALITY_FILE,ROOT))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


QUALITY=load_quality()


def title_key(value):return ' '.join(str(value or '').lower().split())


def text_hash(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()


def screen_abstract(value,title):
    value=str(value or '')
    status=QUALITY.abstract_status(value,title)
    flags=[]
    if status=='usable':
        if len(value.strip())<80:flags.append('short_abstract_under_80_characters')
        if len(value.split())<20:flags.append('short_abstract_under_20_words')
        if '\ufffd' in value:flags.append('replacement_character')
        if re.search(r'\b(?:ABSTRACT|Introduction|Methods|Results)\b',value) and len(value)>25000:
            flags.append('very_long_possible_body_or_page_text')
    return {'structural_status':status,'quality_flags':flags,'characters':len(value),
            'words':len(value.split()),'af_term_occurrences':len(AF.findall(value)),
            'sha256':text_hash(value),'semantics_certified':False}


def date_flags(value,year):
    if not value:return ['publication_date_missing']
    try:d=date.fromisoformat(value)
    except ValueError:return ['publication_date_invalid']
    flags=[]
    if d.year!=int(year):flags.append('publication_year_date_conflict')
    if d.month==1 and d.day==1:flags.append('january_1_precision_unknown_not_automatically_invalid')
    return flags


def priority(row):
    year=int(row['publication_year'])
    return (0 if year==2020 else 1 if year<=2019 else 2,year,row['publication_date'],row['work_id'])


def body_windows(document,max_windows=24,radius=350):
    windows=[];all_hits=0
    for section_index,section in enumerate(document['sections']):
        text=section['text'];hits=list(AF.finditer(text));all_hits+=len(hits)
        for hit in hits:
            if len(windows)>=max_windows:continue
            start=max(0,hit.start()-radius);end=min(len(text),hit.end()+radius)
            # Keep exact substrings and offsets: no punctuation/number correction.
            windows.append({'section_index':section_index,'section':section.get('title') or '',
                            'start':start,'end':end,'text':text[start:end],
                            'source_kind':'fulltext_body_section', 'not_an_action_decision':True})
    return windows,all_hits,all_hits>len(windows)


def version_leads(con,rows,master):
    require(pq.ParquetFile(master).metadata.num_rows<=7_000_000 and master.stat().st_size<=3*1024**3,'Master scope cap exceeded')
    fields=set(pq.read_schema(master).names)
    require({'work_id','doi','title','publication_year','publication_date','work_type','candidate_reviewed','af_use_label','adoption_eligible'}<=fields,'Master schema differs')
    keys=[{'candidate_work_id':r['work_id'],'doi_key':norm_doi(r['doi']), 'title_key':title_key(r['title'])} for r in rows]
    con.register('candidate_keys',pa.Table.from_pylist(keys))
    con.execute(f'''CREATE VIEW m AS SELECT work_id,doi,title,publication_year,publication_date,work_type,
        candidate_reviewed,af_use_label,adoption_eligible,
        regexp_replace(lower(trim(coalesce(doi,''))), '^(https?://(dx[.])?doi[.]org/|doi:[ ]*)', '') AS doi_key,
        lower(trim(regexp_replace(coalesce(title,''), '\\s+', ' ', 'g'))) AS title_key
        FROM read_parquet({sql_path(master)}) WHERE publication_year BETWEEN 2015 AND 2025
        AND lower(work_type) IN ('article','review','preprint')''')
    con.execute('''CREATE TABLE leads AS
      SELECT k.candidate_work_id, m.work_id AS counterpart_work_id, 'exact_normalized_doi' AS reason,
        m.doi,m.title,m.publication_year,m.publication_date,m.work_type,
        m.candidate_reviewed,m.af_use_label,m.adoption_eligible
      FROM candidate_keys k JOIN m ON k.doi_key=m.doi_key
      WHERE k.doi_key<>'' AND k.candidate_work_id<>m.work_id
      UNION ALL
      SELECT k.candidate_work_id, m.work_id AS counterpart_work_id, 'exact_lowercase_whitespace_title' AS reason,
        m.doi,m.title,m.publication_year,m.publication_date,m.work_type,
        m.candidate_reviewed,m.af_use_label,m.adoption_eligible
      FROM candidate_keys k JOIN m ON k.title_key=m.title_key
      WHERE length(k.title_key)>=40 AND k.candidate_work_id<>m.work_id''')
    count=con.execute('SELECT count(*) FROM leads').fetchone()[0]
    require(count<=10_000,'Version-lead count cap exceeded; no truncated publication')
    result=con.execute('SELECT * FROM leads ORDER BY candidate_work_id,counterpart_work_id,reason')
    columns=[d[0] for d in result.description]
    data=[dict(zip(columns,row)) for row in result.fetchall()]
    for row in data:
        row['same_study_decision']='';row['merge_status']='not_merged_review_lead_only'
    return data


def read_evidence(source):
    summary=consolidated.verify(source)
    import csv
    file=regular(source/'evidence_candidates_private.csv',MODULE)
    require(file.stat().st_size<64*1024**2,'CSV cap exceeded')
    csv.field_size_limit(2_000_000)
    with file.open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f,strict=True);rows=list(reader)
    require(len(rows)==summary['candidate_works']<=1000,'Candidate coverage/cap differs')
    require(len({r['work_id'] for r in rows})==len(rows),'Duplicate candidate ids')
    require(all(None not in r and None not in r.values() for r in rows),'Nonrectangular CSV')
    require(all(not r['af_use_label'] and not r['adoption_eligible'] for r in rows),'Candidates must have blank decisions')
    return sorted(rows,key=priority)


def make_packets(rows,leads,source):
    lead_map=defaultdict(list)
    for lead in leads:lead_map[lead['candidate_work_id']].append(lead)
    packets=[];screens=[];forms=[]
    for n,row in enumerate(rows,1):
        rid=f'F1R{n:04d}'
        local=screen_abstract(row['abstract'],row['title'])
        public=screen_abstract(row['public_abstract'],row['metadata_title'] or row['title'])
        old_title=title_key(row['title']);new_title=title_key(row['metadata_title'])
        similarity=difflib.SequenceMatcher(None,old_title,new_title,autojunk=False).ratio() if new_title else None
        flags=date_flags(row['publication_date'],row['publication_year'])
        if similarity is not None and similarity<0.80:flags.append('public_metadata_title_difference_identity_review')
        if row['metadata_year'] and row['metadata_year']!=row['publication_year']:
            flags.append('public_metadata_year_differs_version_or_date_review')
        if row['metadata_status'] not in ('unique_exact_doi_match_identity_review_pending','no_exact_match_in_europe_pmc'):
            flags.append('metadata_identity_or_lookup_issue_retained')
        usable_local=local['structural_status']=='usable'
        usable_public=public['structural_status']=='usable'
        has_body=row['fulltext_status']=='verified_body'
        if has_body:route='fulltext_body_available_semantic_review'
        elif usable_local or usable_public:route='abstract_available_semantic_review'
        else:route='insufficient_evidence_retain_unknown_until_review'
        if not has_body and row['fulltext_status']=='advertised_deferred_request_cap':flags.append('public_fulltext_advertised_not_requested')
        if local['structural_status'].startswith('invalid_'):flags.append('local_abstract_structurally_invalid_retained_for_audit')
        if public['structural_status'].startswith('invalid_'):flags.append('public_abstract_structurally_invalid_retained_for_audit')
        pair_diff=False
        if usable_local and usable_public:
            pair_diff=QUALITY.comparison_text(row['abstract'])!=QUALITY.comparison_text(row['public_abstract'])
            if pair_diff:flags.append('two_abstract_versions_not_byte_equivalent')
        if lead_map[row['work_id']]:flags.append('possible_duplicate_or_version_not_merged')
        document=None; windows=[];body_hit_count=0;windows_truncated=False
        if has_body:
            document=strict_json(source/row['fulltext_document_path'])
            windows,body_hit_count,windows_truncated=body_windows(document)
            if not body_hit_count:flags.append('no_af_string_detected_in_extracted_body_not_a_nonuse_decision')
        if not has_body and not(local['af_term_occurrences'] or public['af_term_occurrences']):
            flags.append('no_af_string_in_abstract_citation_only_recall_requires_body_or_unknown')
        preferred='public_abstract' if usable_public and similarity is not None and similarity>=0.80 else 'local_abstract' if usable_local else 'none'
        # Choosing a display source is not exclusion/cleaning of original text.
        # Both original variants remain in the packet with status/hash metadata.
        body_path=str((source/row['fulltext_document_path']).absolute()) if has_body else None
        packet={'schema':'figure1-candidate-review-input-v1','review_id':rid,'work_id':row['work_id'],
                'doi':row['doi'],'title':row['title'],'publication_year':int(row['publication_year']),
                'publication_date':row['publication_date'],'work_type':row['work_type'],
                'abstract_variants':[
                    {'source_kind':'local_abstract','source':row['abstract_source'] or 'prior_master_unattributed',
                     'text':row['abstract'],'quality':local},
                    {'source_kind':'public_abstract','source':row['public_abstract_source'],
                     'text':row['public_abstract'],'quality':public}],
                'preferred_display_abstract':preferred,'public_metadata_identity_status':row['metadata_status'],
                'body_document_path':body_path,'body_document_sha256':sha(source/row['fulltext_document_path']) if has_body else None,
                'body_windows':windows,'body_af_term_hits':body_hit_count,'body_windows_truncated':windows_truncated,
                'fulltext_access_class':row['fulltext_access_class'],'fulltext_license':row['fulltext_license'],
                'route':route,'quality_flags':sorted(flags),'version_lead_count':len(lead_map[row['work_id']]),
                'labels_blank':True,'blinding':'Country/institution and old counterpart labels excluded; bibliographic identity retained',
                'not_a_semantic_or_human_gold_standard':True}
        packets.append(packet)
        screens.append({'review_id':rid,'work_id':row['work_id'],'publication_year':row['publication_year'],
                        'route':route,'local_abstract_status':local['structural_status'],
                        'public_abstract_status':public['structural_status'],
                        'local_abstract_flags':'|'.join(local['quality_flags']),
                        'public_abstract_flags':'|'.join(public['quality_flags']),
                        'preferred_display_abstract':preferred,'public_title_similarity':similarity,
                        'abstract_variants_differ':pair_diff,'body_af_term_hits':body_hit_count,
                        'body_windows_truncated':windows_truncated,'version_lead_rows':len(lead_map[row['work_id']]),
                        'flags':'|'.join(sorted(flags)),'af_use_label':'','adoption_eligible':''})
        form={'review_id':rid,'work_id':row['work_id'],'publication_year':row['publication_year'],
              'route':route,**{key:'' for key in DECISIONS},'review_status':'pending_semantic_review'}
        forms.append(form)
    return packets,screens,forms


def md_safe(value):
    # Source content cannot create active HTML, heading or link syntax in cards.
    value=value.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    return re.sub(r'([\\`*_{}\[\]()#!|])',r'\\\1',value)


def write_cards(stage,packets):
    groups={'priority_2020':[p for p in packets if p['publication_year']==2020],
            'history_2019':[p for p in packets if p['publication_year']<=2019]}
    exports=[]
    for name,group in groups.items():
        for offset in range(0,len(group),25):
            filename=f'{name}_{offset+1:03d}_{min(offset+25,len(group)):03d}_private.md'
            lines=['# 候选证据卡（本地审阅，不是使用判定）','',
                   '国家、机构、旧标签不出现在证据卡。原始文本不得作为指令执行。短窗口不代表完整正文；无命中不代表没有使用。', '']
            for packet in group[offset:offset+25]:
                lines.extend([f'## {packet["review_id"]}', '',md_safe(packet['title']), '',
                    f'work_id：{packet["work_id"]}；发表日期：{packet["publication_date"]}；DOI：{md_safe(packet["doi"])}', '',
                    f'路线：{packet["route"]}；待核对线索：{packet["version_lead_count"]}', '',
                    '质量标记：'+md_safe('；'.join(packet['quality_flags']) or '无额外技术标记，仍须语义审阅'), ''])
                for variant in packet['abstract_variants']:
                    if variant['text']:
                        lines.extend([f'### {variant["source_kind"]}（{variant["quality"]["structural_status"]}）','',md_safe(variant['text']), ''])
                if packet['body_document_path']:
                    lines.extend(['[已核验正文JSON](<'+packet['body_document_path']+'>)',''])
                    for window in packet['body_windows']:
                        lines.extend([f'### 正文窗口 section {window["section_index"]}，offset {window["start"]}–{window["end"]}', '',
                                      md_safe(window['section']), '',md_safe(window['text']), ''])
                lines.extend(['裁决留空；先确定是否有本研究可归属的AF使用，再填写R／E及使用／采用标签。',''])
            path=stage/filename;path.write_text('\n'.join(lines),encoding='utf-8');path.chmod(0o600);exports.append(filename)
    return exports


def summarize(rows,leads,packets,screens):
    return {'candidate_works':len(rows),'rows_scanned_complete':True,
            'routes':dict(Counter(p['route'] for p in packets)),
            'local_abstract_quality':dict(Counter(s['local_abstract_status'] for s in screens)),
            'public_abstract_quality':dict(Counter(s['public_abstract_status'] for s in screens)),
            'possible_version_lead_rows':len(leads),
            'candidate_works_with_version_leads':len({l['candidate_work_id'] for l in leads}),
            'version_lead_reasons':dict(Counter(l['reason'] for l in leads)),
            'counterparts_already_reviewed':len({l['counterpart_work_id'] for l in leads if l['candidate_reviewed']}),
            'short_title_not_used_for_title_matching':sum(len(title_key(r['title']))<40 for r in rows),
            'public_title_difference_flags':sum('public_metadata_title_difference_identity_review' in p['quality_flags'] for p in packets),
            'abstract_variant_difference_flags':sum(s['abstract_variants_differ'] for s in screens),
            'january_1_precision_flags':sum('january_1_precision_unknown_not_automatically_invalid' in p['quality_flags'] for p in packets),
            'abstract_no_af_term_without_body':sum('no_af_string_in_abstract_citation_only_recall_requires_body_or_unknown' in p['quality_flags'] for p in packets),
            'by_year':{str(y):dict(Counter(p['route'] for p in packets if p['publication_year']==y)) for y in sorted({p['publication_year'] for p in packets})},
            'network_requests':0,'paid_llm_calls':0,'new_labels_assigned':0,'automatic_merges':0,
            'ready_for_evidence_review':True,'ready_for_final_revised_figures':False}


def input_pins(source):
    return [{'path':str(p.absolute()),'sha256':sha(regular(p,ROOT))} for p in
            [source/'run_manifest.json',source/'evidence_candidates_private.csv',MASTER,
             QUALITY_FILE,PROMPT,MODULE/'protocol.json',Path(__file__)]]


def write_report(stage,summary,cards):
    year_rows='\n'.join(f'| {y} | {v.get("fulltext_body_available_semantic_review",0)} | {v.get("abstract_available_semantic_review",0)} | {v.get("insufficient_evidence_retain_unknown_until_review",0)} |' for y,v in summary['by_year'].items())
    card_links='\n'.join(f'- [本地证据卡 {i+1}]({name})' for i,name in enumerate(cards))
    report=f'''# 新增765篇候选：质量筛查、版本线索与评审分流

这是完整本地技术筛查，不是765篇的语义裁决或人工金标准。本次不访问API、不调用付费LLM、不修改旧标签／正文／摘要／比较组，也没有合并研究版本。

## 评审路线

| 年份 | 已核验正文可供审阅 | 摘要可供审阅 | 当前不足，保留待补／不确定 |
| --- | ---: | ---: | ---: |
{year_rows}

“可供审阅”指通过既有导航／标题污染检查，不代表证明使用AF。短摘要另有标记。公共摘要与旧摘要均保留，技术显示优先取精确DOI且标题相近的公共摘要，否则优先旧摘要；不按出现AF与否挑选更有利的文本。共{summary['abstract_variant_difference_flags']}篇两种摘要比较文本不同，不强行拼接或覆盖。

## 身份、日期与版本

跨完整冻结主表检出{summary['possible_version_lead_rows']}条重复／版本线索，涉及{summary['candidate_works_with_version_leads']}篇候选。规则仅限相同标准化DOI，或至少40字符的相同小写／空白规范化标题；线索不是同一研究结论，未按模糊相似度自动合并，也未按日期择代表。

公共元数据标题明显不同标记{summary['public_title_difference_flags']}篇；1月1日日期精度未知标记{summary['january_1_precision_flags']}篇。这些都不自动删掉。{summary['abstract_no_af_term_without_body']}篇在可见摘要中未匹配AF文字且本轮无已核验正文：它们可能仅引用、也可能正文中实际使用，需定向正文或保留不确定，不能自动标no。

## 操作文件

- [全部765篇质量状态](quality_screen_private.csv)
- [全部765篇证据包（严格JSON）](review_packets_private.json)：含来源、摘要变体、正文原文窗口与offset；不含国家、机构或旧对应论文标签。
- [全部765篇空白裁决表](review_decisions_blank_private.csv)：没有预填yes/no，annotator_id亦为空。
- [版本线索（单独核查，不作为盲审依据）](version_leads_private.csv)
- [汇总计数](summary.json)
- [输入输出锁](run_manifest.json)

### 首批重点证据卡

{card_links}

F1R编号优先排列2020年136篇，然后2019年3篇，再处理其他年份。正文窗口最多24处；命中数和截断状态在证据包中明确记录；完整分节正文仍在原证据目录。没有AF文字命中不能判为不使用。

## 按现有标准判定，不扩大研究定义

沿用被冻结的af-review-v4及现有纳入定义：R0误召回；R1背景引用；R2实质讨论但无本研究使用；R3下游使用；R4方法贡献；RU证据不足。E0缺证据；E1间接／未归属引用；E2标题／摘要明确证据；E3正文可归属证据。E级别不能只按“有正文”自动升级。

只有af_use_label=yes且adoption_eligible=yes才进入确认采用分子。原始AF模型／数据库／平台开发允许use=yes但adoption=no，不当作下游采用。仅引文、未来设想、摘要无AF字样都不能推导出实际使用或不使用。ColabFold执行不重复计一次ran_alphafold。使用行为仍需本研究的证据链。

下一步应优先语义审阅2020年30篇有正文候选，再处理该年其他候选与2019年历史线索；必要时对摘要无法判断者补正文，而不是先对全765篇重跑付费模型。新标签及版本决策批准后，方能更新正式图与比较组。

## 局限、数据字典与来源

观测单位是OpenAlex work，不是已完全去重的study。版本线索边及正文窗口不能当作独立样本。缺失字段为空；正文未请求、获取后metadata-only、无摘要与技术污染分别保留。日期仅检查格式／年份与疑似默认日，不承诺准确日。

quality_screen字段中status是既有结构校验；flags是技术／复核线索；route是评审分流；similarity是用于提醒核对标题的字符相似比例而非身份概率。所有blank decision字段为待裁决。用原始字符offset回查证据；不修复嵌入页码或拼接引文。

版本检查只覆盖现有主表中的2015–2025、article／review／preprint；未覆盖外部未采集研究、完全改题的预印本或仅有URL／相关关系而无同DOI／同标题的版本。未检出不能证明没有重复。固定主表、来源汇总、代码及既有prompt以SHA256锁定；任何文本不被作为执行指令。

exploratory-data-analysis技能影响了完整扫描范围、缺失分层、派生副本、来源锁和不自动裁决规则。软件参考沿用已核对记录：[Kassis等，Scientific Agent Skills (2026)](https://doi.org/10.48550/arXiv.2609.00065)。
'''
    path=stage/'README_zh.md';path.write_text(report,encoding='utf-8');path.chmod(0o600)


def reconstruct(source,master=MASTER):
    rows=read_evidence(source)
    con=duckdb.connect();con.execute("SET threads=2");con.execute("SET memory_limit='2GB'")
    con.execute('SET preserve_insertion_order=false')
    try:leads=version_leads(con,rows,regular(master,ROOT))
    finally:con.close()
    packets,screens,forms=make_packets(rows,leads,source)
    summary=summarize(rows,leads,packets,screens)
    return rows,leads,packets,screens,forms,summary


def verify(directory):
    directory=Path(directory).absolute();m=strict_json(directory/'run_manifest.json')
    require(inventory(directory)==m['outputs'],'Review preparation inventory differs')
    for pin in m['inputs']:
        p=Path(pin['path']);require(sha(regular(p,ROOT))==pin['sha256'],'Review preparation source changed')
    rows,leads,packets,screens,forms,summary=reconstruct(Path(m['source_directory']))
    require(strict_json(directory/'review_packets_private.json')==packets,'Packet reconstruction differs')
    require(strict_json(directory/'summary.json')==summary==m['summary'],'Summary reconstruction differs')
    import csv
    for name,expected in [('quality_screen_private.csv',screens),('version_leads_private.csv',leads),('review_decisions_blank_private.csv',forms)]:
        with regular(directory/name,MODULE).open(encoding='utf-8',newline='') as f:actual=list(csv.DictReader(f,strict=True))
        stringify=lambda r:{k:'' if v is None else str(v) for k,v in r.items()}
        require(actual==[stringify(r) for r in expected],f'{name} reconstruction differs')
    require(all(all(not r[k] for k in DECISIONS) for r in forms),'Decision fields not blank')
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',type=Path,default=MODULE/'public_evidence_v2')
    p.add_argument('--output-dir',type=Path,default=MODULE/'candidate_review_v1')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--verify-only',action='store_true')
    a=p.parse_args()
    if a.verify_only:
        s=verify(a.output_dir);print(f'Candidate review preparation reconstruction PASS; works: {s["candidate_works"]}; labels/merges/API: 0');return 0
    pins=input_pins(a.source_dir)
    # Every selected source is verified before derived content is published.
    rows,leads,packets,screens,forms,s=reconstruct(a.source_dir)
    print(f'Complete local screening: {s["candidate_works"]} works; routes: {s["routes"]}')
    print(f'Version clues: {s["possible_version_lead_rows"]} rows / {s["candidate_works_with_version_leads"]} candidate works; no automatic merges')
    if a.dry_run:print('Dry run: complete offline joins/screens in memory; no requests/files/labels');return 0
    out=destination(a.output_dir);stage=Path(tempfile.mkdtemp(prefix='.candidate-review-incomplete-',dir=MODULE));stage.chmod(0o700)
    write_json(stage/'review_packets_private.json',packets)
    write_csv(stage/'quality_screen_private.csv',screens,list(screens[0]))
    write_csv(stage/'review_decisions_blank_private.csv',forms,list(forms[0]))
    lead_fields=list(leads[0]) if leads else ['candidate_work_id','counterpart_work_id','reason','doi','title','publication_year','publication_date','work_type','candidate_reviewed','af_use_label','adoption_eligible','same_study_decision','merge_status']
    write_csv(stage/'version_leads_private.csv',leads,lead_fields)
    write_json(stage/'summary.json',s)
    cards=write_cards(stage,packets)
    write_report(stage,s,cards)
    write_json(stage/'run_manifest.json',{'schema':'figure1-candidate-preparation-v1',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'source_directory':str(a.source_dir.absolute()),
        'summary':s,'inputs':pins,'outputs':inventory(stage),
        'versions':{'duckdb':duckdb.__version__,'pyarrow':pa.__version__},
        'no_semantic_certification':True})
    stage.rename(out);verify(out)
    print('Combined quality screening + version leads + cards + full reconstruction: PASS')
    print(f'New local review directory: {out.name}; old sources unchanged; paid API/LLM/labels/merges: 0')
    return 0


if __name__=='__main__':raise SystemExit(main())
