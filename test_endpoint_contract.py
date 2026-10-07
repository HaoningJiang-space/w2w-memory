import unittest
from endpoint_contract_probe import solve,complete_word_rate


class EndpointTests(unittest.TestCase):
    def test_narrow_serial_output_differs_from_parallel_outputs(self):
        self.assertAlmostEqual(solve('E',.5,2)['total'],1.)
        self.assertAlmostEqual(solve('M_direct',.5,2)['total'],.5)
        self.assertAlmostEqual(solve('M_buffered',.5,2)['total'],1.)

    def test_full_width_serialization_and_parent_capacity(self):
        for n in (1,2,4):
            self.assertAlmostEqual(solve('E',1,n)['total'],1.)
            self.assertAlmostEqual(solve('M_direct',1,n)['total'],1.)
            self.assertAlmostEqual(solve('M_buffered',1,n)['total'],1.)

    def test_fixed_share_and_word_assembly(self):
        self.assertAlmostEqual(solve('F',.25,1)['total'],.25)
        self.assertAlmostEqual(solve('F',.25,4)['total'],1.)
        self.assertEqual(complete_word_rate({0}),0.)
        self.assertAlmostEqual(complete_word_rate({0,1,2,3}),1.)

    def test_switching_budget_is_charged_once(self):
        self.assertAlmostEqual(solve('M_direct',.5,2,.9)['total'],.45)
        self.assertAlmostEqual(solve('M_buffered',.5,2,.9)['total'],.9)


if __name__=='__main__':unittest.main()
