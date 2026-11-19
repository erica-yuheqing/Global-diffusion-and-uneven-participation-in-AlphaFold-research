"""Offline regression suite for whole-study matching, panel scope and handoff fidelity."""
import unittest,tempfile
from common import *
from matching import credit_matrix,stratify
from prepare import evaluate_pilot
from verify import numeric,links

class GiniTests(unittest.TestCase):
    def test_equal(self):self.assertEqual(float(gini([1,1,1])),0)
    def test_zero_countries(self):self.assertAlmostEqual(float(gini([0,0,3])),2/3)
    def test_scale(self):self.assertAlmostEqual(float(gini([0,1,2])),float(gini([0,10,20])))
    def test_matrix(self):np.testing.assert_allclose(gini([[1,1],[0,2]]),[0,.5])
    def test_allzero_undefined(self):self.assertTrue(np.isnan(gini([0,0])))
    def test_negative(self):
        with self.assertRaises(ValueError):gini([-1,2])
    def test_nonfinite(self):
        with self.assertRaises(ValueError):gini([1,np.nan])
    def test_empty(self):
        with self.assertRaises(ValueError):gini([])

class StudyMatchingTests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame([(2021,'article','one','AF','AA|BB',2),(2021,'article','one','AF','',1),(2021,'article','one','C','AA',4),(2021,'article','one','C','',2),(2021,'review','two','AF','BB',1),(2021,'review','two','C','BB',3)],columns=['year','work_type','subfield','group','signature','n'])
    def test_whole_country_set_fraction(self):np.testing.assert_allclose(credit_matrix(['AA|BB','AA',''],['AA','BB']).toarray(),[[.5,.5],[1,0],[0,0]])
    def test_duplicate_country_rejected(self):
        with self.assertRaises(ValueError):credit_matrix(['AA|AA'],['AA','BB'])
    def test_outside_registry_rejected(self):
        with self.assertRaises(ValueError):credit_matrix(['CC'],['AA','BB'])
    def test_count_only_one_stratum(self):
        _,groups,s=stratify(self.fixture(),2021,'count_only');self.assertEqual(len(groups),1);self.assertEqual(s.AF_target.sum(),4)
    def test_composition_separate_layers(self):
        _,groups,s=stratify(self.fixture(),2021,'count_composition');self.assertEqual(len(groups),2);self.assertEqual(s.AF_target.tolist(),[3,1])
    def test_known_country_removes_unknown_not_reassigns(self):
        x,_,s=stratify(self.fixture(),2021,'count_composition_known_country');self.assertTrue(x.signature.ne('').all());self.assertEqual(s.AF_target.sum(),3)
    def test_no_cross_layer_fallback(self):
        x=self.fixture();x.loc[x.group.eq('C')&x.work_type.eq('article'),'n']=1
        _,_,s=stratify(x,2021,'count_composition');self.assertFalse(s.supported.all())
    def test_hypergeom_without_replacement(self):
        rng=np.random.default_rng(19);freq=rng.multivariate_hypergeometric([2,3,1],4,size=1000,method='marginals');self.assertTrue((freq<=[2,3,1]).all());self.assertTrue((freq.sum(axis=1)==4).all())
    def test_hypergeom_credit_conserves_whole_study(self):
        mat=credit_matrix(['AA|BB','AA',''],['AA','BB']);freq=np.array([[2,1,1],[0,4,0]]);credits=np.asarray(mat.T@freq.T).T
        np.testing.assert_allclose(credits,[[2,1],[4,0]]);np.testing.assert_allclose(credits.sum(axis=1),[3,4])
    def test_fixed_AF_differenced_quantiles(self):
        values=np.arange(1,10)/10;AF=.95
        np.testing.assert_allclose(np.quantile(AF-values,[.025,.975]),AF-np.quantile(values,[.975,.025]))
    def test_endpoint_range_not_marginal_subtraction(self):
        a=np.array([0,1,2,3,4]);b=a+.2
        self.assertFalse(np.allclose(np.quantile(b-a,[.025,.975]),np.quantile(b,[.025,.975])-np.quantile(a,[.975,.025])))

class PilotTests(unittest.TestCase):
    def test_unknown_not_TN(self):
        x=pd.DataFrame(dict(metric_eligible=[True]*3,human_af_use_label=['yes','no','no'],human_adoption_eligible=['yes','no','no'],z_af_use_label=['yes','uncertain','no'],z_adoption_eligible=['yes','uncertain','no']))
        _,m=evaluate_pilot(x,'z');self.assertEqual(m['TN'],1);self.assertEqual(m['undecided_or_missing'],1);self.assertEqual(m['precision'],1)
    def test_joint_yes_rule(self):
        x=pd.DataFrame(dict(metric_eligible=[True],human_af_use_label=['yes'],human_adoption_eligible=['yes'],z_af_use_label=['yes'],z_adoption_eligible=['no']))
        _,m=evaluate_pilot(x,'z');self.assertEqual(m['TP'],0);self.assertEqual(m['positive_not_detected'],1)
    def test_unresolved_reference_excluded(self):
        x=pd.DataFrame(dict(metric_eligible=[True,False],human_af_use_label=['yes','uncertain'],human_adoption_eligible=['yes','uncertain'],z_af_use_label=['yes','yes'],z_adoption_eligible=['yes','yes']))
        _,m=evaluate_pilot(x,'z');self.assertEqual(m['evaluated_n'],1)

class LinksTests(unittest.TestCase):
    def root(self,md):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);root=Path(t.name);(root/'a.md').write_text(md);(root/'b.csv').write_text('n\n1');return root
    def test_valid(self):self.assertEqual(len(links(self.root('[b](b.csv)'))),1)
    def test_absolute_rejected(self):
        with self.assertRaises(ValueError):links(self.root('[b](/tmp/b.csv)'))
    def test_escape_rejected(self):
        with self.assertRaises(ValueError):links(self.root('[b](../b.csv)'))
    def test_missing_rejected(self):
        with self.assertRaises(ValueError):links(self.root('[b](c.csv)'))
    def test_external_not_local(self):self.assertEqual(links(self.root('[x](https://example.com)')),[])

class ActualContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (OUT/'provenance/handoff_audit.json').is_file():raise unittest.SkipTest('Actual prepared handoff unavailable')
    def test_independent_numeric_suite(self):self.assertGreater(len(numeric(OUT)),200)
    def test_source_handoff_all23(self):
        x=json.loads((OUT/'provenance/handoff_audit.json').read_text());self.assertEqual(x['status'],'PASS');self.assertGreater(x['check_count'],80)
    def test_main_composition_endpoints_match_document(self):
        x=load(OUT,'matching_summary').query('spec=="count_composition"').set_index('year');self.assertEqual(f'{x.loc[2021,"point"]:.4f}','0.0168');self.assertEqual(f'{x.loc[2025,"point"]:.4f}','0.0194')
    def test_pilot_production_not_historical_ensemble(self):
        x=load(OUT,'Table_S2_pilot_metrics').set_index('system');self.assertEqual(x.loc['production','TP'],103);self.assertEqual(x.loc['ensemble','TP'],100)
    def test_author_blinding_not_holdout(self):
        x=json.loads((OUT/'provenance/author_confirmation.json').read_text());self.assertEqual(x['exact_user_statement'],'人工判读前未查看模型答案');self.assertFalse(x['heldout_validation_confirmed'])
    def test_ED2_known_output_denominator(self):
        x=load(OUT,'ed2a_attributed_composition');self.assertNotIn('Unknown',x.country_code.unique());np.testing.assert_allclose(x.groupby('year').attributed_fraction.sum(),1)
    def test_fixed_two_different_tens(self):
        a=load(OUT,'normalization_country_selection').head(10).country_code.tolist();b=load(OUT,'ed2a_attributed_composition').country_code.drop_duplicates().tolist()[:10];self.assertNotEqual(a,b)
    def test_country_code_AF_not_tag(self):self.assertIn('AF',load(OUT,'country_year_AF_normalization').country_code.unique())
    def test_country_code_NA_not_missing(self):self.assertIn('NA',load(OUT,'country_year_AF_normalization').country_code.unique())
    def test_25_panel_source_tables(self):self.assertEqual(len(load(OUT,'panel_source_index')),25)
    def test_main_labels_a_d_no_titles(self):
        x=json.loads((OUT/'provenance/main_artist_contract.json').read_text());self.assertEqual(x['panel_labels'],list('abcd'));self.assertFalse(x['titles'])
    def test_no_original_draw_certification(self):
        x=json.loads((OUT/'provenance/handoff_audit.json').read_text());self.assertTrue(x['original_draws_not_in_lightweight_handoff'])

if __name__=='__main__':unittest.main()
