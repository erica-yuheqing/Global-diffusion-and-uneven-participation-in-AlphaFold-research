"""Requirement-focused regression tests, isolated copies, no upstream writes."""
import unittest,tempfile,shutil,json,sys
from pathlib import Path
from common import *
from verify import validate_inputs
BASE=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent.parent
sys.argv=sys.argv[:1]
class Contracts(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.out=Path(self.t.name)
  shutil.copytree(BASE/'inputs',self.out/'inputs');(self.out/'provenance').mkdir();shutil.copy2(BASE/'provenance/original_inputs_manifest.json',self.out/'provenance/original_inputs_manifest.json')
 def tearDown(self):self.t.cleanup()
 def mutate(self,rel,fn):
  p=self.out/rel;df=pd.read_csv(p,keep_default_na=False);fn(df);df.to_csv(p,index=False)
  m=json.loads((self.out/'provenance/original_inputs_manifest.json').read_text())
  for x in m['input_files']:
   if x['copy']==rel:x['sha256']=sha(p)
  dump(self.out/'provenance/original_inputs_manifest.json',m)
 def test_frozen_inputs(self):self.assertGreater(len(validate_inputs(self.out)),100)
 def test_reject_false_raw_gap(self):
  self.mutate('inputs/source_data/Figure1b_lower.csv',lambda x:x.__setitem__('delta_gini',x.delta_gini+.01))
  with self.assertRaisesRegex(ValueError,'raw difference identity'):validate_inputs(self.out)
 def test_reject_AF_varying_matching(self):
  self.mutate('inputs/source_data/Figure1c.csv',lambda x:x.__setitem__('point',x.point+.001))
  with self.assertRaisesRegex(ValueError,'matched point identity'):validate_inputs(self.out)
 def test_reject_all_study_composition_denominator(self):
  self.mutate('inputs/source_data/ED2a.csv',lambda x:x.__setitem__('attributed_fraction',x.fraction))
  with self.assertRaisesRegex(ValueError,'composition uses attributed fraction'):validate_inputs(self.out)
 def test_reject_lost_Namibia(self):
  self.mutate('inputs/tables/Table_S4_country_year_R_first_observation.csv',lambda x:x.__setitem__('country_code',x.country_code.replace('NA','')))
  with self.assertRaisesRegex(ValueError,'Namibia retained'):validate_inputs(self.out)
 def test_reject_unsupported_layer(self):
  self.mutate('inputs/tables/matching_stratum_support.csv',lambda x:x.__setitem__('non_AF_available',0))
  with self.assertRaisesRegex(ValueError,'all target strata supported'):validate_inputs(self.out)
 def test_endpoint_uses_2025_not_2024(self):
  # Changing only the 2024 endpoint row must not substitute it for the 2025 check.
  self.mutate('inputs/tables/concentration_endpoint_sensitivity.csv',lambda x:x.__setitem__('point',x.point.where(x.end.ne(2024),(x.lower+x.upper)/2)))
  self.assertTrue(validate_inputs(self.out)['raw paired endpoint estimate'])
 def test_main_artist_contract(self):
  c=json.loads((BASE/'provenance/main_artist_contract.json').read_text())
  self.assertEqual(c['a_ylim'],[.89,.96]);self.assertEqual(c['b_ylim'],[-.003,.055]);self.assertEqual(c['b_markers'],['D','o']);self.assertFalse(c['smoothing']);self.assertFalse(c['secondary_axes'])
 def test_source_numeric_strings_unchanged(self):
  import csv
  rows=pd.read_csv(BASE/'provenance/panel_input_mapping.csv')
  for row in rows.itertuples():
   with (BASE/row.input).open(newline='',encoding='utf-8-sig') as f:orig=list(csv.DictReader(f))
   with (BASE/row.source_data).open(newline='',encoding='utf-8-sig') as f:export=list(csv.DictReader(f))
   self.assertEqual([{k:r[k] for k in orig[0]} for r in export],orig)
 def test_no_global_ED_or_S_collision(self):
  r=pd.read_csv(BASE/'manuscript/global_figure_numbering.csv')
  self.assertFalse(r.duplicated(['type','global']).any())
if __name__=='__main__':unittest.main()
