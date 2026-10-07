import unittest
import numpy as np
from w2w.validation.verify_egress_reachability import service


class EgressReachabilityTests(unittest.TestCase):
    def test_address_permission_cannot_create_receiver_path(self):
        y=np.tile(np.eye(2,dtype=bool),(2,1,1))
        for active in ((0,),(0,1)):
            self.assertAlmostEqual(service(y,'unique',active)['rate_per_active'],1)
            self.assertAlmostEqual(service(y,'flexible',active)['rate_per_active'],1)
            impossible=service(y,'striped',active)
            self.assertGreater(impossible['missing_active_byte_classes'],0)
            self.assertFalse(impossible['floor_one_feasible'])
            self.assertEqual(impossible['rate_per_active'],0)

    def test_aggregation_requires_reachable_parallel_service(self):
        y=np.ones((2,2,2),bool)
        self.assertAlmostEqual(service(y,'striped',(0,))['rate_per_active'],2)
        self.assertAlmostEqual(service(y,'striped',(0,1))['rate_per_active'],1)
        self.assertAlmostEqual(service(y,'striped',(0,),serial=True)['rate_per_active'],1)


if __name__=='__main__':unittest.main()
