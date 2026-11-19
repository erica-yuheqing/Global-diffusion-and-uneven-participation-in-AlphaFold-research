import unittest
import numpy as np
import pandas as pd
from support import *
from benchmark import reference_counts,assign_rates,expected_probabilities,summarize
from authors import paper_state,institution_state,fixed_probabilities
from initial_models import design,ridge_fit,contrasts

def exposure():return pd.DataFrame(dict(institution_id=['i','i'],interval=[1,2],subfield=['x','x'],year=[2021,2022],n=[2,3]))
def base():return pd.DataFrame(dict(institution_id=['i','empty'],quintile=[1,5],sustained=[True,False],repeat=[True,False],opportunity_timing_complete=[True,True]))
def counts():return pd.DataFrame(dict(subfield=['x','x'],year=[2021,2022],all_n=[10,10],af_n=[1,1],comparison_n=[9,9],unknown_n=[0,0]))

class BenchmarkTests(unittest.TestCase):
    def test_formula(self):
        x=expected_probabilities(assign_rates(exposure(),counts(),minimum=1),base()).set_index('institution_id')
        self.assertAlmostEqual(x.loc['i','expected'],(1-.9**2)*(1-.9**3))
    def test_empty_is_zero(self):
        x=expected_probabilities(assign_rates(exposure(),counts(),minimum=1),base()).set_index('institution_id');self.assertEqual(x.loc['empty','expected'],0)
    def test_missing_is_not_zero(self):
        x=assign_rates(exposure(),counts(),minimum=1);x.loc[0,'p']=np.nan
        self.assertTrue(np.isnan(expected_probabilities(x,base()).set_index('institution_id').loc['i','expected']))
    def test_bad_timing_not_zero(self):
        b=base();b.loc[1,'opportunity_timing_complete']=False
        self.assertTrue(np.isnan(expected_probabilities(assign_rates(exposure(),counts(),minimum=1),b).set_index('institution_id').loc['empty','expected']))
    def test_probability_one(self):
        x=assign_rates(exposure(),counts(),minimum=1);x['p']=1
        self.assertEqual(expected_probabilities(x,base()).set_index('institution_id').loc['i','expected'],1)
    def test_probability_zero(self):
        x=assign_rates(exposure(),counts(),minimum=1);x['p']=0
        self.assertEqual(expected_probabilities(x,base()).set_index('institution_id').loc['i','expected'],0)
    def test_sparse_pooling(self):self.assertTrue(assign_rates(exposure(),counts(),minimum=100).rate_level.eq('pooled_calendar_year').all())
    def test_minimum_boundary(self):self.assertTrue(assign_rates(exposure(),counts(),minimum=10).rate_level.eq('subfield_calendar_year').all())
    def test_reference_duplicates_rejected(self):
        r=pd.DataFrame(dict(study_id=['s','s'],subfield=['x','x'],year=[2021,2021],label_state=['AF','AF']))
        with self.assertRaises(ValueError):reference_counts(r)
    def test_unknown_not_negative(self):
        r=pd.DataFrame(dict(study_id=['a','b','c'],subfield=['x']*3,year=[2021]*3,label_state=['AF','comparison','unknown_label']))
        c=reference_counts(r);self.assertEqual(c.comparison_n.iloc[0],1);self.assertEqual(c.unknown_n.iloc[0],1)
    def test_shared_paper_fully_removed(self):
        e=exposure().iloc[:1];c=counts().iloc[:1].copy();c[['all_n','af_n','comparison_n']]=[3,1,2]
        removed=pd.DataFrame(dict(institution_id=['i'],subfield=['x'],year=[2021],all_n=[2],af_n=[1],comparison_n=[1],unknown_n=[0]))
        rate=assign_rates(e,c,minimum=1,leaveout=removed);self.assertEqual(rate.p.iloc[0],0)
    def test_unknown_bounds(self):
        c=counts();c['all_n']=12;c['unknown_n']=2
        lo=assign_rates(exposure(),c,minimum=1,probability='lower').p
        mid=assign_rates(exposure(),c,minimum=1).p
        hi=assign_rates(exposure(),c,minimum=1,probability='upper').p
        self.assertTrue((lo<=mid).all() and (mid<=hi).all())
    def test_missing_rate_no_denominator(self):
        c=counts();c[['all_n','af_n','comparison_n','unknown_n']]=0
        self.assertTrue(assign_rates(exposure(),c).p.isna().all())

class AuthorTests(unittest.TestCase):
    def test_positive_overlap_with_partial_metadata(self):self.assertEqual(paper_state({'a'},{'a','b'},False,False),'linked')
    def test_no_overlap_needs_complete_initial(self):self.assertEqual(paper_state({'a'},{'b'},False,True),'unresolved')
    def test_no_overlap_needs_complete_later(self):self.assertEqual(paper_state({'a'},{'b'},True,False),'unresolved')
    def test_unlinked_observed_complete(self):self.assertEqual(paper_state({'a'},{'b'},True,True),'unlinked')
    def test_empty_author_set_not_negative(self):self.assertEqual(paper_state(set(),{'b'},True,True),'unresolved')
    def test_strict_sensitivity(self):self.assertEqual(paper_state({'a'},{'a'},False,True,True),'unresolved')
    def test_linked_only(self):self.assertEqual(institution_state(['linked','linked']),'Linked-only')
    def test_unlinked_only(self):self.assertEqual(institution_state(['unlinked']),'Unlinked-only')
    def test_mixed(self):self.assertEqual(institution_state(['linked','unlinked']),'Mixed')
    def test_mixed_not_erased_by_unknown(self):self.assertEqual(institution_state(['linked','unlinked','unresolved']),'Mixed')
    def test_partial_linked_not_linked_only(self):self.assertEqual(institution_state(['linked','unresolved']),'Unresolved')
    def test_no_paper_not_author_sample(self):
        with self.assertRaises(ValueError):institution_state([])
    def test_fixed_two_paper_exact(self):np.testing.assert_allclose(fixed_probabilities(['linked','unlinked','unresolved'],2),[0,1/3,0,2/3])
    def test_all_papers_category_exact(self):np.testing.assert_allclose(fixed_probabilities(['linked','unlinked','unresolved'],3),[0,1,0,0])
    def test_fixed_sample_cannot_exceed_papers(self):
        with self.assertRaises(ValueError):fixed_probabilities(['linked'],2)

class WindowAndModelTests(unittest.TestCase):
    def test_quintiles_ties(self):
        values=np.repeat(np.arange(1,11),10);q,c=quintiles(values)
        self.assertTrue(pd.DataFrame({'v':values,'q':q}).groupby('v').q.nunique().eq(1).all())
    def test_no_forced_five_groups(self):
        with self.assertRaises(ValueError):quintiles([1]*100)
    def test_missing_scale_not_zero(self):
        with self.assertRaises(ValueError):quintiles([1,2,np.nan,4])
    def test_probability_standardization_not_odds_ratio(self):
        x=np.column_stack([np.ones(4),[0,0,1,1]]);b=np.array([0,np.log(3)])
        a,c,_,_=contrasts(x,b,1);self.assertAlmostEqual(a,.5);self.assertAlmostEqual(c,.75)
    def test_ridge_nonseparation_and_finite(self):
        x=np.column_stack([np.ones(100),np.arange(100)/100]);y=np.r_[np.zeros(50),np.ones(50)]
        b,_=ridge_fit(x,y);self.assertTrue(np.isfinite(b).all());self.assertGreater(b[1],0)
    def test_calendar_windows_initial_excluded(self):
        dates=pd.to_datetime(['2020-01-15','2020-01-20','2021-01-15','2021-01-16','2022-01-15','2022-01-16'])
        e=pd.DataFrame(dict(study_id=[f's{i}' for i in range(6)],institution_id=['i']*6,event_date=dates,
          confirmed_af=[True]*6,possible_af_only=[False]*6,confirmed_evidence_year=dates.year,
          within_study_first_date_unresolved=[False]*6,earliest_undated_confirmed_year=[np.nan]*6,
          earliest_version_evidence_year=dates.year,undated_confirmed_versions=[0]*6))
        scale=pd.DataFrame(dict(institution_id=['i'],baseline_papers=[1.],fixed_cohort_ge1=[True]))
        h,z=oldcode().history(e,scale);self.assertEqual(h.co_initial.iloc[0],1);self.assertEqual(h.bin1.iloc[0],2);self.assertEqual(h.bin2.iloc[0],2)
        e['event_date']=e.event_date.dt.to_period('M').dt.to_timestamp('M');h,z=oldcode().history(e,scale)
        self.assertEqual(h.co_initial.iloc[0],2);self.assertEqual(h.bin1.iloc[0],2);self.assertEqual(h.bin2.iloc[0],2)
    def test_month_window_includes_leap_february_end(self):
        dates=pd.to_datetime(['2023-02-01','2024-02-29','2025-02-28'])
        e=pd.DataFrame(dict(study_id=['a','b','c'],institution_id=['i']*3,event_date=dates,
          confirmed_af=[True]*3,possible_af_only=[False]*3,confirmed_evidence_year=dates.year,
          within_study_first_date_unresolved=[False]*3,earliest_undated_confirmed_year=[np.nan]*3,
          earliest_version_evidence_year=dates.year,undated_confirmed_versions=[0]*3))
        scale=pd.DataFrame(dict(institution_id=['i'],baseline_papers=[1.],fixed_cohort_ge1=[True]))
        h,z=monthly_history(e,scale)
        self.assertEqual(h.month12_end.iloc[0],pd.Timestamp('2024-02-29'))
        self.assertEqual(h.window_end.iloc[0],pd.Timestamp('2025-02-28'))
        self.assertEqual(h.bin1.iloc[0],1);self.assertEqual(h.bin2.iloc[0],1)

class ActualDataTests(unittest.TestCase):
    @unittest.skipUnless((OUT/'tables/panel_b_observed_expected.parquet').exists(),'Prepared data not present')
    def test_primary_cohort_and_b_N_match(self):
        x=load(OUT,'panel_b_observed_expected');self.assertEqual(x.N.sum(),2339)
        self.assertTrue(x.incomplete_expected.eq(0).all())
    @unittest.skipUnless((OUT/'tables/panel_d_author_continuity.parquet').exists(),'Author data not present')
    def test_d_full_partition_and_not_sustained_only(self):
        x=load(OUT,'panel_d_author_continuity');self.assertEqual(len(x),1255);self.assertTrue(x.institution_id.is_unique)
        self.assertEqual(int(x.later_studies.sum()),3244)
    @unittest.skipUnless((OUT/'tables/initial_model_diagnostics.parquet').exists(),'Model data not present')
    def test_no_fake_CI(self):
        x=load(OUT,'panel_c_initial_use');bad=x.CI_status.ne('released_component_cluster_95CI')
        self.assertTrue(x.loc[bad,['CI_low','CI_high','difference_CI_low','difference_CI_high']].isna().all().all())
    @unittest.skipUnless((OUT/'tables/author_fixed_count_sensitivity.parquet').exists(),'Author sensitivity not present')
    def test_common_fixed_count_cohort_constant(self):
        x=load(OUT,'author_fixed_count_sensitivity');x=x[x.scope.eq('common_at_least5')]
        self.assertTrue(x.groupby('quintile').N_eligible.nunique().eq(1).all())

if __name__=='__main__':unittest.main()
