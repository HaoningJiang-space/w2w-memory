import itertools
import unittest
from w2w.synthesis.contract_selection import population_rates,choose


class ContractSelectionTests(unittest.TestCase):
    def test_population_matches_exhaustive_subsets(self):
        for n in (4,6,8):
            for k in range(1,n+1):
                means=[];commons=[]
                for s in itertools.combinations(range(n),k):
                    rates=[.75 if (c^1) in s else 1.5 for c in s]
                    means.append(sum(rates)/k);commons.append(min(rates))
                got=population_rates(1.5,.75,k,n)
                self.assertAlmostEqual(got['mean'],sum(means)/len(means))
                self.assertAlmostEqual(got['common'],sum(commons)/len(commons))

    def test_contract_changes_choice_with_same_budget(self):
        direct=dict(id='wide_direct',costs=dict(export_lane_bits=192,storage_bits=256),
                    rates=dict(optimistic=(1.5,1),fluid=(1.5,.75),executed=(1,.5)))
        buffered=dict(id='narrow_buffered',costs=dict(export_lane_bits=128,storage_bits=768),
                      rates=dict(optimistic=(1,1),fluid=(1,1),executed=(1,1)))
        args=([direct,buffered],dict(export_lane_bits=192,storage_bits=768),[(36,1.)])
        self.assertEqual(choose(*args,'optimistic')['id'],'wide_direct')
        self.assertEqual(choose(*args,'fluid')['id'],'narrow_buffered')
        self.assertEqual(choose(*args,'executed',floor=1)['id'],'narrow_buffered')
        self.assertIsNone(choose([direct],args[1],args[2],'executed',floor=1))


if __name__=='__main__':unittest.main()
