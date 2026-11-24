import unittest

from gpu_ml.sre_preview import build_preview


class SREPreviewTests(unittest.TestCase):
    def test_drift_forecast_never_uses_the_current_observation(self):
        drift = build_preview('drift')['devices'][0]
        normal = build_preview('normal')['devices'][0]
        observed = drift['series']['gpu_temp']
        control = normal['series']['gpu_temp']
        first_change = next(i for i, (a, b) in enumerate(zip(observed, control)) if a != b)
        dynamic = drift['trends']['gpu_temp']['local_trend']
        unchanged = normal['trends']['gpu_temp']['local_trend']
        self.assertEqual(dynamic['expected'][:first_change + 1], unchanged['expected'][:first_change + 1])
        self.assertNotEqual(dynamic['scores'][first_change], unchanged['scores'][first_change])
        self.assertTrue(dynamic['periods'])
        self.assertFalse(unchanged['periods'])
        self.assertNotEqual(dynamic['periods'], drift['trends']['gpu_temp']['historical_level']['periods'])

    def test_correlated_conditions_and_missing_data(self):
        preview = build_preview('fleet')
        devices = {device['id']: device for device in preview['devices']}
        rule = devices['rule']['white']
        period = rule['periods'][-1]
        self.assertEqual(period['confirmed'] - period['start'] + 1, preview['confirmation'])
        for condition in rule['conditions']:
            self.assertGreaterEqual(condition['values'][period['confirmed']], condition['threshold'])

        black = devices['joint']['black']
        point = black['periods'][-1]['confirmed']
        self.assertGreaterEqual(black['scores'][point], 1)
        self.assertAlmostEqual(sum(row[point] for row in black['contributions'].values()), 1, places=3)

        gap = devices['gap']
        point = gap['quality']['periods'][-1]['confirmed']
        self.assertEqual(gap['quality']['validFields'][point], 4)
        self.assertIsNone(gap['black']['scores'][point])
        self.assertIsNone(gap['white']['scores'][point])
        self.assertIsNone(gap['trends']['power']['local_trend']['scores'][point])
