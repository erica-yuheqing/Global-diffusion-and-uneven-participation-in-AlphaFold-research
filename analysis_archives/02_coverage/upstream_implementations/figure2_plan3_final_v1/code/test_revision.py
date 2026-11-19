"""Finite-enumeration and counterexample tests; no API or data writes."""
import unittest
import itertools
import math
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from benchmark import Sampler,log_none,active_cells,ratio,summarize_coverage,make_weights,holm
from support import tertiles

class Counts(unittest.TestCase):
    def test_hypergeometric_enumeration(self):
        for n in range(1,9):
            for k in range(n+1):
                combos=list(itertools.combinations(range(n),k))
                for m in range(n+1):
                    exact=sum(not any(i<m for i in s) for s in combos)/len(combos)
                    self.assertAlmostEqual(float(np.exp(log_none(n,k,m))),exact,places=12)
    def test_impossible(self): self.assertTrue(np.isneginf(log_none(5,3,3)))
    def test_zero_success(self): self.assertEqual(float(log_none(5,0,5)),0.)
    def test_zero_exposure(self): self.assertEqual(float(log_none(5,5,0)),0.)
    def test_all_success(self): self.assertEqual(float(np.exp(log_none(5,5,1))),0.)
    def test_large_combinations_finite(self): self.assertTrue(np.isfinite(log_none(1000000,5000,50)))
    def test_invalid(self):
        with self.assertRaises(ValueError):log_none(3,4,1)
    def test_sampler_exactK(self):
        codes=np.array([0,0,0,1,1,2,2]);z=np.array([1,0,0,0,0,1,1]);s=Sampler(codes,z)
        for j in range(50):
            sample=s.draw(np.random.default_rng(j))
            np.testing.assert_array_equal(np.bincount(codes[sample],minlength=3),[1,0,2])
            self.assertEqual(len(sample),len(set(sample)))
    def test_unknown_labels_rejected(self):
        with self.assertRaises(ValueError):Sampler([0,0],[1,-1])
    def test_reproducible(self):
        s=Sampler([0,0,0,1,1],[1,0,0,1,0])
        np.testing.assert_array_equal(s.draw(np.random.default_rng(7)),s.draw(np.random.default_rng(7)))
    def test_sampler_uniform_small(self):
        s=Sampler([0,0,0],[1,0,0]);r=np.random.default_rng(9)
        counts=np.bincount([s.draw(r)[0] for _ in range(6000)],minlength=3)
        self.assertLess(np.max(abs(counts-2000)),160)
    def test_shared_paper_moves_jointly(self):
        m=csr_matrix(([1,1,1],([0,0,1],[0,6,12])),shape=(2,18))
        got=active_cells(m.indptr,m.indices,np.array([0]),np.arange(3),3)
        np.testing.assert_array_equal(got[:,0],[1,1,0])
    def test_integer_any_not_credit_threshold(self):
        m=csr_matrix(([1,1],([0,1],[0,0])),shape=(2,6))
        got=active_cells(m.indptr,m.indices,np.array([0,1]),np.array([0]),1)
        self.assertEqual(got[0,0],1)
    def test_outside_baseline_paper_kept_in_sampler(self):
        # One of two papers has no fixed-baseline institution, but still receives a label.
        m=csr_matrix(([1],([0],[0])),shape=(2,6));s=Sampler([0,0],[1,0])
        r=np.random.default_rng(2);active=[]
        for _ in range(1000):active.append(active_cells(m.indptr,m.indices,s.draw(r),np.array([0]),1)[0,0])
        self.assertAlmostEqual(np.mean(active),.5,delta=.05)
    def test_all_empty_fixed_cell_zero(self):
        m=csr_matrix((3,6));got=active_cells(m.indptr,m.indices,np.array([0,1]),np.array([0]),1)
        np.testing.assert_array_equal(got,0)
    def test_years_not_mixed(self):
        m=csr_matrix(([1,1],([0,1],[1,5])),shape=(2,6))
        got=active_cells(m.indptr,m.indices,np.array([0,1]),np.array([0]),1)
        self.assertEqual(got[0,1],1);self.assertEqual(got[0,5],1);self.assertEqual(got.sum(),2)

class Aggregation(unittest.TestCase):
    def test_country_cell_encoding_cannot_overflow_int8(self):
        codes=pd.Categorical(['C49'],categories=[f'C{i}' for i in range(80)]).codes.astype(np.int64)
        self.assertEqual(int((codes*3)[0]),147)
    def test_ties_not_split(self):
        v=np.array([1,1,1,2,3,4,5,6,7]);g,cuts,valid=tertiles(v)
        self.assertEqual(len(set(g[v==1])),1);self.assertTrue(valid)
    def test_collapsed_cutpoints_invalid(self): self.assertFalse(tertiles([1]*40+[2,3])[2])
    def test_boundary_ties_lower(self):
        g,_,_=tertiles([1,2,3,4,5,6,7]);self.assertEqual(g[2],0);self.assertEqual(g[4],1)
    def test_country_weights_not_group_weights(self):
        c=pd.DataFrame(dict(context=['Low','Low','High'],fractional_context=['Low','Low','High'],eligible_20=[True]*3))
        w=make_weights(c)
        np.testing.assert_allclose(w[0],[1/3]*3);np.testing.assert_allclose(w[1],[.5,.5,0])
    def test_ratio_of_means_not_mean_ratios(self):
        x=np.zeros((2,3,6));x[:,0,:]=np.array([.1,.4])[:,None];x[:,2,:]=np.array([.2,.8])[:,None]
        w=np.array([[.5,.5]]);a,r,g,d=summarize_coverage(x,w)
        self.assertAlmostEqual(r[0,0],.5);self.assertAlmostEqual(g[0,0],25.)
        x[1,2,:]=.4
        a,r,g,d=summarize_coverage(x,w)
        self.assertNotAlmostEqual(r[0,0],(.5+1)/2)
    def test_zero_denominator_undefined(self): self.assertTrue(np.isnan(ratio(0,0)))
    def test_zero_numerator_valid(self): self.assertEqual(float(ratio(0,.1)),0.)
    def test_gap_identity(self):
        l,h=.15,.5;self.assertAlmostEqual(100*(h-l),100*h*(1-float(ratio(l,h))))
    def test_joint_contrast_preserves_dependence(self):
        d=np.array([[-1.,-2.],[0.,0.],[1.,2.]])
        paired=d[:,0]-d[:,1]
        self.assertLess(np.var(paired),np.var(d[:,0])+np.var(d[:,1]))
    def test_centered_reference_not_point_CI(self):
        draw=np.array([1.,2.,3.]);mu=2.;obs=6.
        centered=draw-mu;excess=obs-mu
        np.testing.assert_equal(centered,[-1,0,1]);self.assertEqual(excess,4.)
    def test_negative_excess_not_gap_narrowing(self):
        observed,expected=3.,5.;self.assertGreater(observed,0);self.assertLess(observed-expected,0)
    def test_holm(self): np.testing.assert_allclose(holm([.01,.04,.03]),[.03,.06,.06])
    def test_undefined_R_does_not_prevent_G(self):
        a=np.zeros((1,3,6));_,r,g,d=summarize_coverage(a,np.ones((1,1)))
        self.assertTrue(np.isnan(r).all());np.testing.assert_equal(g,0.)
    def test_constant_denominator(self):
        n=20;active=np.array([0,1,4,0,5,8]);a=active/n
        self.assertEqual(a[3],0);self.assertEqual(n,20)
    def test_zero_MC_variance_not_proof_of_determinism(self):
        q=1-float(np.exp(log_none(100000,1,1)))
        self.assertGreater(q,0);self.assertLess(q,.0001)
        # A rare event can be absent from all pilot draws while exact expectation is positive.
        self.assertFalse(q<1e-9 or q>1-1e-9)

class ReleaseTests(unittest.TestCase):
    def test_TIFF_rational_DPI_serializable_after_conversion(self):
        import json
        from PIL.TiffImagePlugin import IFDRational
        dpi=[float(x) for x in [IFDRational(600,1),IFDRational(600,1)]]
        self.assertEqual(json.loads(json.dumps(dpi)),[600.,600.])
    def test_renderer_ratio_dependency(self):
        import figures
        self.assertTrue(callable(figures.ratio))
    def test_independent_check_ratio_dependency(self):
        import finalize
        self.assertTrue(callable(finalize.ratio))
    def test_portable_link(self):
        from finalize import check_links
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'a.md').write_text('[b](b.md)');(root/'b.md').write_text('ok')
            self.assertEqual(check_links(root),1)
    def test_missing_link_rejected(self):
        from finalize import check_links
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'a.md').write_text('[bad](absent.md)')
            with self.assertRaises(ValueError):check_links(root)
    def test_escape_link_rejected(self):
        from finalize import check_links
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'a.md').write_text('[bad](/etc/hosts)')
            with self.assertRaises(ValueError):check_links(root)

if __name__=='__main__':unittest.main()
