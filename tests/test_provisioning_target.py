from fractions import Fraction
import unittest

from w2w.synthesis.provisioning_target import target_design


class TargetTests(unittest.TestCase):
    def test_rx_capacity_changes_the_selected_interface(self):
        limited, _ = target_design(192, rx_depth=2)
        supplied, _ = target_design(192, rx_depth=3)
        self.assertEqual(limited.endpoint.widths[2], 256)
        self.assertEqual(supplied.endpoint.widths[2], 192)
        self.assertEqual(str(supplied.home_fraction), '4/7')
        for rx in (1, True, 2.5):
            with self.assertRaisesRegex(ValueError, 'Home256'):
                target_design(128, rx_depth=rx)

    def test_targets_select_word_lifetime_and_capacity_boundaries(self):
        for n, width, depth, fraction in ((128, 128, 1, '4/5'), (160, 128, 1, '2/3'), (192, 192, 2, '4/7')):
            design, cert = target_design(n)
            self.assertEqual(design.endpoint.widths[2], width)
            self.assertEqual(design.endpoint.depths[2], depth)
            self.assertEqual(str(design.home_fraction), fraction)
            for row in cert['candidates']:
                if row['width_bits'] < width:
                    self.assertLess(Fraction(row['relaxed_max_rate']), Fraction(cert['target_rate']))

    def test_full_gain_requires_full_width_at_n192(self):
        design, cert = target_design(192, 1)
        self.assertEqual(cert['target_rate'], '2')
        self.assertEqual(design.endpoint.widths[2], 256)
        self.assertEqual(design.endpoint.mode, 'direct')

    def test_degenerate_reference_is_not_a_retention_target(self):
        for n, eta in ((96, Fraction(3, 4)), (128, 0), (192, 2)):
            with self.assertRaises(ValueError):
                target_design(n, eta)


if __name__ == '__main__':
    unittest.main()
