import unittest,tempfile
from pathlib import Path
import duckdb,pandas as pd,numpy as np
import networks
from shared_weights import keys,weights_from_keys
from outcomes import supported
from partners import partner_summary
from model_math import design,diagnose
import network_analysis
from types import SimpleNamespace
class ScientificCounterexamples(unittest.TestCase):
 def test_context_keeps_ID_and_P_D_identical_AF_records(self):
  f=pd.DataFrame({'institution_id':['A','A','B'],'year':[2021]*3,'subfield':['S']*3,'work_type':['article']*3,'study_id':['W1','W2','W3'],'work_id':['W1','W2','W3'],'country':['GB']*3,'group':['L']*3,'parent_field':['F']*3,'V_i':[1]*3,'af_row':[0,1,2],'cell':[0,1,2],'journal_position':[50.]*3,'high_journal75':[0.]*3,'x_log':[1.,1.,2.],'partner_mean_percentile':[30.,np.nan,90.],'coverage':[1.,.5,1.],'n_other_institutions':[1]*3,'n_scored_partners':[1]*3,'n_outside_boundary':[0]*3,'n_unknown_baseline':[0]*3,'m_all':[2]*3,'network_id':['baseline_B2']*3,'focal_in_roster':[True]*3,'observed_author_roster_covered':[True]*3,'single_institution':[False]*3})
  aw=np.ones((3,1));y=np.array([[3.],[99.],[9.]]);bundle=SimpleNamespace(metric='journal_position',binary='high_journal75',outcome='journal',matrices={'default':(None,None,None,None,np.ones(3,bool))},point={'default':(aw,y,y,np.ones((3,1)))})
  with tempfile.TemporaryDirectory() as td:
   old=network_analysis.D;network_analysis.D=Path(td)
   try:
    ctx=network_analysis.context(bundle,f,'fixture_partner','partner');p=ctx['point'].set_index('institution_id')
    self.assertEqual(set(ctx['frame'].study_id),{'W1','W3'});self.assertEqual(p.loc['A','D_i'],3);self.assertEqual(p.loc['A','x'],30);self.assertEqual(p.loc['A','n_AF'],1)
   finally:network_analysis.D=old
 def test_same_study_weight_across_subsets_order_and_chunks(self):
  full=weights_from_keys(keys(['A','B','C']),0,100)
  subset=weights_from_keys(keys(['C','A']),0,100);np.testing.assert_array_equal(subset,full[[2,0]])
  np.testing.assert_array_equal(np.c_[weights_from_keys(keys(['A','B','C']),0,40),weights_from_keys(keys(['A','B','C']),40,60)],full)
 def test_positive_exp_distribution(self):
  w=weights_from_keys(keys(['A','B','C']),0,20000);self.assertTrue((w>0).all());self.assertAlmostEqual(w.mean(),1,delta=.03);self.assertAlmostEqual(w.var(),1,delta=.07)
 def test_observed_isolate_is_not_unknown_history(self):
  e=pd.DataFrame({'institution_u':['A'],'institution_v':['B'],'fractional_weight':[1.]})
  n=networks.graph_scores(['A','B','C','D'],[1,1,1,0],e).set_index('institution_id')
  self.assertEqual(n.loc['C','degree'],0);self.assertTrue(pd.isna(n.loc['D','degree']));self.assertTrue(pd.isna(n.loc['D','degree_percentile']));self.assertAlmostEqual(n.loc['C','degree_percentile'],100/6)
 def test_projection_fractional_normalization_and_unknown_node(self):
  with tempfile.TemporaryDirectory() as td:
   old=networks.D;networks.D=Path(td);c=duckdb.connect()
   c.register('i',pd.DataFrame({'institution_id':['A','B','C'],'country':['GB']*3,'group':['L','M','H'],'V_i':[1,2,3],'baseline_eligible':[True]*3}))
   c.register('s',pd.DataFrame({'study_id':['P']*3,'institution_id':['A','B','X'],'year':[2018]*3,'B2_eligible':[True,True,False]}));c.register('r',pd.DataFrame({'study_id':['P'],'n_institutions':[3],'observed_author_roster_covered':[True]}))
   try:
    a=networks.build(c,'fixture',2015,2019);e=pd.read_parquet(Path(td)/'networks/fixture/edges.parquet');n=pd.read_parquet(Path(td)/'networks/fixture/nodes.parquet')
    self.assertEqual(len(e),1);self.assertEqual(e.fractional_weight.iloc[0],1);self.assertEqual(a['unknown_nodes'],1);self.assertTrue(n.loc[n.institution_id.eq('C'),'degree'].isna().all())
   finally:networks.D=old;c.close()
 def test_outcome_specific_control_pools_are_not_forced_joint(self):
  z=pd.DataFrame({'institution_id':['A'],'year':[2021],'subfield':['S'],'work_type':['article'],'J':[80.],'C':[90.]});r=pd.concat([z.assign(J=50.,C=np.nan),z.assign(J=np.nan,C=20.)])
  zz,rr=supported(z,r,['J','C']);self.assertEqual(len(zz),1);self.assertEqual(len(rr),2)
 def test_immature_window_calendar_anniversary(self):
  date=pd.Timestamp('2024-02-29');anniversary=date+pd.DateOffset(months=12);self.assertEqual(anniversary,pd.Timestamp('2025-02-28'));self.assertFalse(pd.Timestamp('2025-02-28')<anniversary)
 def test_focal_exclusion_unscored_partner_and_single_not_zero(self):
  r=partner_summary('A',['A','B','X'],{'A':10,'B':80},{'A','B'},True)
  self.assertEqual(r['n_other_institutions'],2);self.assertTrue(np.isnan(r['partner_mean_percentile']));self.assertEqual(r['partial_partner_mean_percentile'],80);self.assertEqual(r['coverage'],.5)
  s=partner_summary('A',['A'],{'A':10},{'A'},True);self.assertTrue(s['single_institution']);self.assertTrue(np.isnan(s['partner_mean_percentile']))
 def test_incomplete_observed_authors_do_not_pass_main_partner_gate(self):
  r=partner_summary('A',['A','B'],{'A':20,'B':80},{'A','B'},False);self.assertEqual(r['coverage'],1);self.assertTrue(np.isnan(r['partner_mean_percentile']))
 def test_sparse_weighted_model_recovers_known_slope_and_rejects_rank_failure(self):
  rng=np.random.default_rng(3);inst=np.repeat(np.arange(60),2);n=len(inst);x=rng.normal(size=60)[inst]
  z=pd.DataFrame({'institution_id':['I'+str(i) for i in inst],'study_id':['W'+str(i) for i in range(n)],'group':np.array(['L','M','H'])[inst%3],'country':np.where(inst%2,'US','GB'),'year':np.tile([2021,2022],60),'parent_field':['F']*n,'work_type':['article']*n,'x_log':x,'V_i':inst+1,'partner_mean_percentile':rng.uniform(0,100,n)})
  X,names,_=design(z);d,b,_=diagnose(X,np.repeat(.5,n),2+3*x,60,120);self.assertTrue(d['estimable']);self.assertAlmostEqual(b[names.index('log_degree')],3,places=7)
  z['x_log']=np.log1p(z.V_i);X,_,_=design(z);d,b,_=diagnose(X,np.repeat(.5,n),2+3*x,60,120);self.assertFalse(d['estimable']);self.assertIsNone(b)
if __name__=='__main__':unittest.main()
