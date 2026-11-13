"""Scientific distribution tests and historical-source regression protection."""
import hashlib,math,unittest
from pathlib import Path
import numpy as np
from scipy import stats
from designer_generator import algorithms,core

class GeneratorScientificTests(unittest.TestCase):
    def test_historical_source_is_unchanged(self):
        source=Path(__file__).with_name('original_generators.py').read_text(encoding='utf8').split('import numpy as np\n\n',1)[1]
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),'a05865e011e7e6aba00e64a901a8927c814d4d936c62f58a156488c1525eb7d7')

    def test_gamma_law_support_moments_and_cdf(self):
        n=50000
        epsilon=math.sqrt(math.log(2/1e-6)/(2*n))
        for method,fn in [('A',algorithms.gamma_a),('GD',algorithms.gamma_gd)]:
            for a in (1.01,3.,5.4525349587,200.):
                with self.subTest(method=method,a=a):
                    x,counters=fn(n,a,np.random.default_rng(20261113))
                    self.assertTrue(np.isfinite(x).all() and np.all(x>0))
                    self.assertLess(abs(x.mean()-a),6*math.sqrt(a/n))
                    variance_se=math.sqrt((2*a*a+6*a)/n)
                    self.assertLess(abs(x.var(ddof=1)-a),6*variance_se)
                    self.assertLess(stats.ks_1samp(x,lambda z:stats.gamma.cdf(z,a)).statistic,epsilon)
                    self.assertGreaterEqual(counters['proposals'],n)

    def test_gd_includes_hat_stage_and_exponential_shape_one(self):
        x,counters=algorithms.gamma_gd(30000,1.,np.random.default_rng(117))
        self.assertGreater(counters['hat_proposals'],0)
        self.assertLess(stats.ks_1samp(x,stats.expon.cdf).statistic,.02)
        self.assertLess(abs(x.mean()-1),.035)

    def test_reflection_support_cdf_quantile_and_moments(self):
        a,b,theta=3.,17.,2.
        self.assertEqual(core.model_cdf(b,a,b,theta),1.)
        self.assertEqual(core.model_cdf(b+10,a,b,theta),1.)
        self.assertEqual(core.model_pdf(b,a,b,theta),0.)
        self.assertEqual(core.model_pdf(b+10,a,b,theta),0.)
        probabilities=np.array([.001,.05,.5,.95,.999])
        quantiles=core.model_quantile(probabilities,a,b,theta)
        self.assertTrue(np.all(quantiles<b))
        np.testing.assert_allclose(core.model_cdf(quantiles,a,b,theta),probabilities,atol=1e-12)
        t=core.theoretical(a,b,theta)
        self.assertEqual(t['mean'],11.)
        self.assertEqual(t['variance'],12.)
        self.assertAlmostEqual(t['skew'],-2/math.sqrt(3))
        for method in ['A','GD']:
            r=core.generate(method,20000,a,b,theta,71)
            self.assertEqual(r['support_violations'],0)
            self.assertTrue(np.all(r['values']<=b))
            self.assertLess(abs(r['values'].mean()-11),.15)
            self.assertLess(stats.ks_1samp(r['values'],lambda z:core.model_cdf(z,a,b,theta)).statistic,.025)

    def test_reproducibility_and_global_rng_isolation(self):
        initial=np.random.get_state()
        for method in ['A','GD']:
            a=core.generate(method,200,3.,17.,2.,40)
            b=core.generate(method,200,3.,17.,2.,40)
            np.testing.assert_array_equal(a['values'],b['values'])
            self.assertEqual(a['proposals'],b['proposals'])
        current=np.random.get_state()
        self.assertEqual(initial[0],current[0]); np.testing.assert_array_equal(initial[1],current[1]); self.assertEqual(initial[2:],current[2:])

    def test_unique_observations_have_no_unique_empirical_mode(self):
        self.assertEqual(core.summary([1,3,5,7])['modes'],[])
        self.assertEqual(core.summary([1,1,3,3,5])['modes'],[1.,3.])

    def test_real_fit_retains_negative_skew_and_honest_model_comparison(self):
        data=core.load_no2(); models={r['key']:r for r in core.compare_models(data)}
        a,b,theta=core.fit_parameters(data)
        self.assertGreater(b,data.max()); self.assertTrue(1<a<1000 and theta>0)
        self.assertLess(models['reflected_gamma']['D_data'],models['right_gamma']['D_data'])
        self.assertLess(models['skew_normal']['AIC'],models['reflected_gamma']['AIC'])
        self.assertLess(models['reflected_gamma']['skew'],0)
        self.assertLess(abs(models['reflected_gamma']['variance']/data.var(ddof=1)-1),.02)

    def test_sum_comparison_is_removed_for_different_sizes(self):
        data=np.arange(1,11,dtype=float)
        runs={'A':core.generate('A',20,3.,17.,2.,40)}
        table=core.comparison_table(data,runs,3.,17.,2.)
        self.assertNotIn('Сумма, мкВ',table['Показатель'].tolist())

    def test_invalid_parameters_fail_before_generation(self):
        for args in [('A',0,3.,17.,2.,40),('A',100,1.,17.,2.,40),('GD',100,3.,17.,0.,40),('A',100,3.,17.,2.,-1)]:
            with self.subTest(args=args),self.assertRaises(ValueError): core.generate(*args)

if __name__=='__main__': unittest.main()
