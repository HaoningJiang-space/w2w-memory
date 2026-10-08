import unittest
from w2w.analysis.static_direction_support import maximum_nonhome


class StaticDirectionSupportTests(unittest.TestCase):
    def test_one_way_chain_cannot_carry_balanced_nonhome_bytes(self):
        result=maximum_nonhome([[1,1,0],[0,1,1],[0,0,1]])
        self.assertTrue(result['acyclic'])
        self.assertEqual(result['maximum_mean_nonhome_fraction'],0)

    def test_reciprocal_pair_and_cycle_allow_nonhome_residency(self):
        pair=maximum_nonhome([[1,1,0],[1,1,0],[0,0,1]])
        cycle=maximum_nonhome([[1,1,0],[0,1,1],[1,0,1]])
        self.assertAlmostEqual(pair['maximum_mean_nonhome_fraction'],2/3)
        self.assertAlmostEqual(cycle['maximum_mean_nonhome_fraction'],1)


if __name__=='__main__':unittest.main()
