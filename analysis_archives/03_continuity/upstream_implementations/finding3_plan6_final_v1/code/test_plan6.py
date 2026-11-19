import unittest
import pandas as pd
import numpy as np
from common import combine,transition,configuration,phase
from analyze import standardize

class Rules(unittest.TestCase):
    def test_unlisted_not_zero(self):self.assertEqual(combine(['not_established','not_listed_legacy']),'not_listed_legacy')
    def test_unknown_not_zero(self):self.assertEqual(combine(['not_established','uncertain']),'uncertain')
    def test_quarantine_precedes_positive(self):self.assertEqual(combine(['supported','quarantined']),'quarantined')
    def test_or_supported(self):self.assertEqual(combine(['supported','not_assessed']),'supported')
    def test_all_assessed_zero(self):self.assertEqual(combine(['not_established','not_established']),'not_established')
    def test_phase_boundary(self):self.assertEqual(phase(pd.Series(pd.to_datetime(['2021-06-30','2021-07-01','2024-04-30','2024-05-01']))).tolist(),['Pre-AF2','AF2','AF2','AF3'])
    def test_calendar_not_365_days(self):self.assertEqual(pd.Timestamp('2023-02-28')+pd.DateOffset(months=12),pd.Timestamp('2024-02-28'))
    def test_monthend_clamps(self):self.assertEqual(pd.Timestamp('2024-08-31')+pd.DateOffset(months=6),pd.Timestamp('2025-02-28'))
    def test_zero_net_can_hide_changes(self):
        x=pd.DataFrame(dict(pair_order_uncertain=[False]*4,entry_x=[0,0,1,1],followup_x=[0,1,0,1]));r=transition(x,'x');self.assertEqual(r['net_change_pp'],0);self.assertEqual(r['change_rate'],.5)
    def test_unknown_excluded_category_only(self):
        x=pd.DataFrame(dict(pair_order_uncertain=[False]*3,entry_x=[0,np.nan,1],followup_x=[1,1,np.nan]));r=transition(x,'x');self.assertEqual(r['N'],1);self.assertEqual(r['n01'],1)
    def test_uncertain_order_excluded(self):
        x=pd.DataFrame(dict(pair_order_uncertain=[True,False],entry_x=[0,1],followup_x=[1,1]));r=transition(x,'x');self.assertEqual(r['N'],1);self.assertEqual(r['n11'],1)
    def test_different_conditional_denominators(self):
        x=pd.DataFrame(dict(pair_order_uncertain=[False]*5,entry_x=[0,0,0,1,1],followup_x=[0,0,1,0,1]));r=transition(x,'x');self.assertEqual(r['retention_N'],2);self.assertEqual(r['new_N'],3)
    def test_zero_event_does_not_drop_support(self):
        x=pd.DataFrame(dict(g=['a']*10+['b']*10,s=['same']*20,y=[0]*20));a,b,c=standardize(x,'g','y',['s'],['a','b'],'t','m');self.assertTrue(a.fraction.eq(0).all());self.assertTrue(a.retained_N.eq(10).all())
    def test_sparse_no_extrapolation(self):
        x=pd.DataFrame(dict(g=['a']*10+['b']*9,s=['same']*19,y=[1]*19));a,b,c=standardize(x,'g','y',['s'],['a','b'],'t','m');self.assertTrue(a.fraction.isna().all());self.assertTrue(a.retained_N.eq(0).all())
    def test_common_weights(self):
        x=pd.DataFrame([dict(g=g,s=s,y=y) for g,s,n,y in [('a','x',10,0),('a','z',30,1),('b','x',30,1),('b','z',10,0)] for _ in range(n)])
        a,b,c=standardize(x,'g','y',['s'],['a','b'],'t','m');self.assertTrue(a.fraction.eq(.5).all());self.assertTrue(c.weight.eq(.5).all())
    def test_config_never_ci_claim(self):self.assertIn('no unvalidated',configuration()['uncertainty'])

if __name__=='__main__':unittest.main()
