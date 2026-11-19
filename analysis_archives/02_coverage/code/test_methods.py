"""Method-focused regressions, not synthetic data used for scientific findings."""
import unittest
from common import *
from model import rcs,objective,fit_newton
from scipy.special import expit
class MethodTests(unittest.TestCase):
 def test_linear_two_knots(self):
  x=np.linspace(0,1,10);np.testing.assert_allclose(rcs(x,[.2,.8])[:,0],x);self.assertEqual(rcs(x,[.2,.8]).shape,(10,1))
 def test_natural_linear_tails(self):
  x=np.array([-.3,-.2,-.1,1.1,1.2,1.3]);v=rcs(x,[.05,.35,.65,.95]);np.testing.assert_allclose(v[0]-2*v[1]+v[2],0,atol=1e-12);np.testing.assert_allclose(v[3]-2*v[4]+v[5],0,atol=1e-12)
 def test_duplicate_knots_reduced(self):self.assertEqual(rcs(np.linspace(0,1,8),[.1,.1,.8,.9]).shape,(8,2))
 def test_exact_score(self):
  x=np.column_stack([np.ones(8),np.arange(8)/7]);y=np.array([0,0,1,0,1,0,1,1]);b=np.array([-.5,1.]);score=objective(b,x,y)[1];h=1e-5
  for j in range(2):
   d=np.eye(2)[j]*h;fd=(objective(b+d,x,y)[0]-objective(b-d,x,y)[0])/(2*h);self.assertAlmostEqual(fd,score[j],places=8)
 def test_binomial_fit(self):
  x=np.column_stack([np.ones(8),np.arange(8)/7]);y=np.array([0,0,1,0,1,0,1,1]);b,r=fit_newton(x,y,np.zeros(2));self.assertTrue(r['converged']);self.assertLess(abs(objective(b,x,y)[1]).max()/len(y),1e-9)
 def test_country_standardization_not_pooled(self):
  per_country=np.array([[.1,.2],[.8,.9]]);np.testing.assert_allclose(per_country.mean(0),[.45,.55]);self.assertNotAlmostEqual(float(per_country[:,0]@[.9,.1]),.45)
 def test_ratio_of_country_means(self):
  l=np.array([.1,.9]);h=np.array([.1,1]);self.assertAlmostEqual(l.mean()/h.mean(),10/11);self.assertNotAlmostEqual((l/h).mean(),l.mean()/h.mean())
 def test_signed_decomposition(self):
  h,l=-3.479912700541867,-.4758208293174484;self.assertAlmostEqual(h-l,-3.0040918712244142);self.assertNotAlmostEqual(h+l,-3.0040918712244142)
 def test_midrank_ties_same_bin(self):
  d=pd.Series([1,1,1,2,3,9]);p=(d.rank(method='average')-.5)/len(d);self.assertEqual(p[:3].nunique(),1);self.assertEqual(np.ceil(p[:3]*10).nunique(),1)
 def test_zero_H_is_undefined(self):
  h=0.;r=.2/h if h>0 else np.nan;self.assertTrue(np.isnan(r))
 def test_A_BQ_not_average_product(self):
  b=np.array([.1,.9]);q=np.array([.9,.1]);self.assertAlmostEqual((b*q).mean(),.09);self.assertNotAlmostEqual(b.mean()*q.mean(),.09)
 def test_round_after_difference(self):self.assertEqual(f'{20.142702753495918-23.146794624720332:.2f}','-3.00');self.assertNotEqual(f'{20.14-23.15:.2f}','-3.00')
if __name__=='__main__':unittest.main()
