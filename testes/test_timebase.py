import math
import unittest

from interface.rta.common import settings, Problem
from interface.rta.timebase import TIMEBASE, floor_time, next_time, valid_time


class TimebaseTests(unittest.TestCase):
    def test_values_confirmed_by_physical_readback(self):
        for requested, actual in [(206e-6,205e-6),(207e-6,205e-6),(208e-6,205e-6),
                (209e-6,205e-6),(199e-6,198e-6),(101e-6,100e-6),
                (2.01e-6,2e-6),(5.19e-9,5.1e-9),(10.1e-9,10e-9),(19.9e-9,19.8e-9)]:
            with self.subTest(requested=requested):
                self.assertEqual(floor_time(requested),actual)

    def test_steps_change_at_band_boundaries(self):
        for before, after in [(198e-6,200e-6),(200e-6,205e-6),(205e-6,210e-6),
                              (495e-6,500e-6),(500e-6,510e-6),(19.8e-9,20e-9)]:
            with self.subTest(before=before):
                self.assertEqual(next_time(before),after)

    def test_unsupported_values_are_rejected_before_configuration(self):
        for value in [206e-6,207e-6,208e-6,209e-6,1.01e-3,5.19e-9,math.nan]:
            with self.subTest(value=value), self.assertRaises(Problem):
                settings({"time_div":value})

    def test_equivalent_units_and_physical_limits(self):
        for value in [210e-6,.21e-3,210000e-9,5e-9,500]:
            self.assertTrue(valid_time(value),value)
            self.assertEqual(settings({"time_div":value})["time_div"],value)
        for value in [4.9e-9,501,0]:
            with self.assertRaises(Problem):
                settings({"time_div":value})

    def test_shared_grid_is_complete_and_contiguous(self):
        bands=TIMEBASE["bands"]
        self.assertEqual(bands[0]["start_ps"],5000)
        self.assertEqual(bands[-1]["end_ps"],500*10**12)
        for previous, current in zip(bands,bands[1:]):
            self.assertEqual(previous["end_ps"],current["start_ps"])
        for b in bands:
            self.assertEqual((b["end_ps"]-b["start_ps"]) % b["step_ps"],0)
            self.assertTrue(valid_time(b["start_ps"]/1e12))
            self.assertTrue(valid_time((b["end_ps"]-b["step_ps"])/1e12))
