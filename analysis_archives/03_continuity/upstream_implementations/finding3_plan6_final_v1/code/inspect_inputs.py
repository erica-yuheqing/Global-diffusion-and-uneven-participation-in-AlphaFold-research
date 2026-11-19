from pathlib import Path
import pyarrow.parquet as pq
import json
ROOT=Path(__file__).resolve().parents[3]
paths=[ROOT/'analysis/nhb_revision_v1/out_v2'/f'{n}.parquet' for n in ['works_eligible','work_institutions','author_institution_membership','authorships']]
paths += [ROOT/'analysis/nhb_03/revision_v9/finding3_plan5_final_v1/tables'/f'{n}.parquet' for n in ['institution_pairs','followup_relations','original_institution_events','selected_work_author_ids','selected_work_author_institutions','author_work_quality']]
paths += [ROOT/'analysis/nhb_revision_v1/baseline_features_v1/baseline_subfield_dictionary.parquet']
for p in paths:
    q=pq.ParquetFile(p);print(json.dumps(dict(path=str(p),rows=q.metadata.num_rows,columns=str(q.schema_arrow)),ensure_ascii=False))
