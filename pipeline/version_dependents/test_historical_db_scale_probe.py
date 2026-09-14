import unittest

from .historical_db_scale_probe import estimate, fit_nonnegative


class ReloadEstimateTests(unittest.TestCase):
    def test_known_fixed_and_row_costs_count_every_date(self):
        trials=[]
        for rows in (8000000,2000000,2000000,8000000):
            trials.append({'rows':rows,'input_seconds':2+.5*rows/1e6,'probe_seconds':8+2*rows/1e6})
        dates=[{'rows':1000000},{'rows':2000000},{'rows':8000000}]
        result=estimate(trials,dates,7)
        self.assertEqual(result['dates'],3)
        self.assertEqual(result['rows'],11000000)
        self.assertAlmostEqual(result['central_seconds'],64.5)
        self.assertEqual(result['pair_sensitivity_seconds'],[64.5,64.5])
        self.assertEqual(result['dates_below_small_sample'],1)

    def test_cache_inversion_does_not_produce_negative_costs(self):
        model=fit_nonnegative([(2000000,30),(8000000,10)])
        self.assertGreaterEqual(model['fixed_seconds_per_date'],0)
        self.assertGreaterEqual(model['seconds_per_million_rows'],0)
        self.assertAlmostEqual(model['fixed_seconds_per_date'],20)
        self.assertEqual(model['seconds_per_million_rows'],0)


if __name__=='__main__':unittest.main()
