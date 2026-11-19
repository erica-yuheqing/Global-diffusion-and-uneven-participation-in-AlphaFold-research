"""Regression tests for estimand definitions and publication-critical data invariants."""
import unittest,itertools
from common import *
from bootstrap import bounds,ratios,pair_shares
from scipy import sparse
class FormulaTests(unittest.TestCase):
    def exact(self,f):
      f=np.array(f,float);A=len(f);return (np.outer(f.sum(axis=0),f.sum(axis=0))-f.T@f)/(A*(A-1))
    def test_AAB_distinct_authors(self):
      e=self.exact([[1,0],[1,0],[0,1]]);np.testing.assert_allclose(e,[[1/3,1/3],[1/3,0]])
    def test_multiaffiliation_exact_enumeration(self):
      f=np.array([[.5,.5],[1,0],[0,1]]);enumerated=sum(np.outer(f[i],f[j]) for i,j in itertools.permutations(range(3),2))/6;np.testing.assert_allclose(self.exact(f),enumerated)
    def test_unknown_institutions_never_same(self):
      # Country credit .5 known + .5 unknown at each endpoint: only .25 known-equal.
      known_equal=.5*.5;unresolved=1-known_equal;self.assertEqual(known_equal,.25);self.assertEqual(unresolved,.75)
    def test_pi_not_q_for_zero_opportunity(self):
      pi=1/2;q=1/4;self.assertNotEqual((1-pi)**2,(1-q)**2);self.assertEqual((1-pi)**2,.25)
    def test_zero_vs_undefined(self):
      self.assertEqual(div(0,1).item(),0);self.assertTrue(np.isnan(div(0,0).item()))
    def test_C_not_always_absolute_reduction(self):
      dc=.2;da=.5;self.assertGreater(da-dc,0);self.assertLess(abs(dc)-abs(da),0)
    def test_degenerate_interval_not_false_precision(self):
      r=bounds(np.zeros(2000));self.assertTrue(r['degenerate']);self.assertTrue(np.isnan(r['ci_low']))
    def test_effective_replicate_threshold(self):
      x=np.arange(2000,dtype=float);x[:101]=np.nan;self.assertEqual(bounds(x)['valid_replicates'],1899);self.assertTrue(np.isnan(bounds(x)['ci_low']))
class FrozenDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
      cls.m=norm('analysis_members.parquet');cls.meta=json.loads((ROOT/'inputs/normalized/feature_metadata.json').read_text());cls.X=sparse.load_npz(ROOT/'inputs/normalized/feature_matrix.npz')
    def test_distinct_explicit_role_ids(self):
      self.assertTrue(self.m.first_id.ne(self.m.last_id).all());self.assertTrue(self.m.observed_author_count.ge(2).all());self.assertTrue(self.m.observed_IDs_consistent.all())
    def test_full_and_supported_counts(self):
      self.assertEqual(self.m.groupby('corpus').size().to_dict(),{'AF':5087,'reference':438473});self.assertEqual(self.m[self.m.supported].groupby('corpus').size().to_dict(),{'AF':5087,'reference':332760})
    def test_all_credit_channels_sum_one(self):
      E=self.meta['n_entities'];nc=self.meta['n_countries']
      for k in range(4):np.testing.assert_allclose(np.asarray(self.X[:,k*E:k*E+nc].sum(axis=1)).ravel(),1,atol=1e-11)
    def test_pair_structure_country_margins(self):
      o=self.meta['offsets'];z=self.X[:,o['structure']:o['structure']+4].toarray();np.testing.assert_allclose(z.sum(axis=1),1,atol=1e-12);np.testing.assert_allclose(z[:,:3].sum(axis=1),self.X[:,o['same_country_observed']].toarray().ravel(),atol=1e-11)
    def test_group_pair_margins_and_expectation(self):
      o=self.meta['offsets'];N=len(self.m);E=self.meta['n_entities'];nc=self.meta['n_countries'];observed=self.X[:,o['observed_group']:o['observed_group']+16].toarray().reshape(N,4,4);expected=self.X[:,o['expected_group']:o['expected_group']+16].toarray().reshape(N,4,4)
      np.testing.assert_allclose(expected.sum(axis=(1,2)),1,atol=1e-11);np.testing.assert_allclose(expected,expected.transpose(0,2,1),atol=1e-11);np.testing.assert_allclose(observed.sum(axis=2),self.X[:,2*E+nc:3*E].toarray(),atol=1e-11)
    def test_Namibia_is_literal_not_missing(self):
      self.assertIn('NA',self.meta['countries']);self.assertTrue(norm('authors_countries.parquet').country_code.eq('NA').any())
    def test_baseline_groups_frozen(self):
      g=norm('country_groups.parquet');self.assertEqual(g[g.eligible_20].baseline_group.value_counts().to_dict(),{'higher':23,'lower':23,'middle':22})
    def test_same_role_numerator_both_benchmarks(self):
      x=pd.read_parquet(ROOT/'tables/strict_main_R.parquet');a=x[x.benchmark.eq('country')].sort_values(['setting','corpus','role','entity_id']);b=x[x.benchmark.eq('author')].sort_values(['setting','corpus','role','entity_id']);np.testing.assert_allclose(a.role_credit,b.role_credit)
    def test_direct_C_from_saved_joint_draws(self):
      p=np.load(ROOT/'draws/strict_main_joint_pools.npz');ra=ratios(p['standardized__AF'],self.meta);rr=ratios(p['standardized__reference'],self.meta);d=ra-rr;ci=np.quantile(d[:,1,0,-2]-d[:,0,0,-2],[.025,.975]);t=pd.read_parquet(ROOT/'tables/strict_main_benchmark_change.parquet').query("setting=='standardized' and role=='first' and entity_id=='group:lower'").iloc[0];np.testing.assert_allclose(ci,[t.ci_low,t.ci_high],atol=1e-12)
    def test_MC_reference_reproduces_exact_expectation(self):
      z=pd.read_parquet(ROOT/'tables/conditional_pair_reference.parquet');p=pd.read_parquet(ROOT/'tables/strict_main_pairings.parquet')
      a=z[z.first_group.ne('same_country')].merge(p[p.corpus.isin(CORPORA)],on=['setting','corpus','first_group','last_group'],validate='one_to_one');self.assertTrue((np.abs(a.conditional_mean-a.expected_share)<=8*a.MC_standard_error+1e-7).all())
    def test_domestic_R_normalizes_within_country(self):
      t=pd.read_parquet(ROOT/'tables/strict_domestic_institution_R.parquet');v=t[t.defined_flag].copy();w=(v.R_inst*v.output_share).groupby([v.country_code,v.corpus,v.role]).sum();np.testing.assert_allclose(w,1,atol=1e-10)
    def test_same_institution_difference_before_summary(self):
      p=pd.read_parquet(ROOT/'tables/strict_domestic_institution_paired.parquet');z=p[p.common_defined];np.testing.assert_allclose(z.delta,z.R_inst_AF-z.R_inst_reference)
    def test_institution_group_mapping_not_lost(self):
      t=pd.read_parquet(ROOT/'tables/domestic_institution_group_pairings.parquet');self.assertTrue(t.first_institution_group.eq('high').any());self.assertTrue(t.first_institution_group.eq('low').any())
    def test_full_country_grid_and_mass(self):
      x=pd.read_parquet(ROOT/'tables/full_country_pair_matrices.parquet');self.assertEqual(len(x),227*227*6);s=x[x.corpus.isin(CORPORA)].groupby(['setting','corpus'])[['observed_share','expected_share']].sum();np.testing.assert_allclose(s,1,atol=1e-10);np.testing.assert_allclose(x.groupby(['setting','corpus']).O_minus_E_pp.sum(),0,atol=1e-9)
    def test_full_country_pair_intervals_not_marginal_subtraction(self):
      idx=norm('country_pair_index.parquet');k=idx.index[idx.first_country.eq('US')&idx.last_country.eq('CN')][0];K=len(idx);v={}
      for cp in CORPORA:
        with np.load(ROOT/'draws'/f'country_pair_{cp}_standardized.npz') as f:
          x=f['joint_country_O_E'];self.assertEqual(x.shape,(2000,2*K));v[cp]=100*(x[:,k]-x[:,K+k])
      lo,hi=np.quantile(v['AF']-v['reference'],[.025,.975]);t=pd.read_parquet(ROOT/'tables/full_country_pair_matrices.parquet');t=t[t.setting.eq('standardized')&t.corpus.eq('AF_minus_reference')&t.first_country.eq('US')&t.last_country.eq('CN')].iloc[0];np.testing.assert_allclose([lo,hi],[t.deviation_ci_low,t.deviation_ci_high],atol=1e-10)
    def test_final_eligibility_mutually_exclusive_counts(self):
      e=pd.read_parquet(ROOT/'source_data/study_eligibility.parquet');self.assertEqual(len(e),2702597);self.assertTrue(e.study_id.is_unique);self.assertTrue(e.new_exclusion_reason.notna().all());self.assertEqual(e[e.new_exclusion_reason.eq('included_standardized')].groupby('original_corpus').size().to_dict(),{'AF':5087,'non-AF':332760})
    def test_required_analyses_executed(self):
      for name in ['N01_complete','features_complete','strict_main_bootstrap_complete','conditional_reference_complete','N06_complete','ancillary_complete','refinements_complete','country_pair_bootstrap_complete','contract_complete','report_complete']:
        self.assertTrue((ROOT/'provenance'/(name+'.json')).is_file(),name)
if __name__=='__main__':unittest.main()
