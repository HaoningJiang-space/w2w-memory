"""Architectural conservation and legality checks, not another performance matrix."""
import unittest
from dataclasses import replace
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory,matched_vertical_budget,cell_format


class ArchitectureV3(unittest.TestCase):
    def test_matched_physical_machine(self):
        a,b=vertical_memory('central'),vertical_memory('distributed')
        proof=matched_vertical_budget(a,b)
        r=inventory(a)
        self.assertTrue(proof['passed'])
        self.assertEqual(r['compute']['clusters'],16)
        self.assertEqual(r['compute']['pes'],65536)
        self.assertEqual(r['compute']['sram_bytes'],3*1024**3)
        self.assertEqual(r['native']['capacity_bytes'],8*1024**3)
        self.assertEqual(r['vertical']['data_bits'],16384)
        self.assertEqual(inventory(b)['collection']['wire_bit_um']*2,r['collection']['wire_bit_um'])
        spec=compile_machine(b)
        self.assertEqual(len(spec.tiles),16)
        self.assertEqual(len(spec.memories),16)
        self.assertTrue(all(p.delay_ps>0 for p in a.collection_paths))

    def test_regions_and_execution_resources_are_independent(self):
        s=vertical_memory()
        s=replace(s,compute_clusters=s.compute_clusters[:-1])
        self.assertEqual(len(compile_machine(s).tiles),15)
        self.assertEqual(len(s.routers),16)
        self.assertEqual(len(s.dram_domains),128)

    def test_stitch_is_short_and_internal_path_paid(self):
        s=vertical_memory()
        boundary=[c for c in s.lateral_links if len(c.segments)>1]
        self.assertTrue(boundary)
        self.assertTrue(all(c.segments[1].length_um==100 for c in boundary))
        self.assertTrue(all(c.length_um>10000 and c.fine_hops==65 for c in boundary))
        self.assertTrue(all(len(s.physical_graph.route(a.id,b.id))>0
            for a in s.routers for b in s.routers if a!=b))

    def test_resource_and_position_rejections(self):
        s=vertical_memory()
        with self.assertRaises(ValueError):
            replace(s,routers=(replace(s.routers[0],position_um=(999999,0)),*s.routers[1:]))
        with self.assertRaises(ValueError):
            replace(s,lateral_links=s.lateral_links[:-1])
        with self.assertRaises(ValueError):
            replace(s,gateways=(replace(s.gateways[0],staging_bytes=4096),*s.gateways[1:]))

    def test_metadata_expands_for_more_than_64_nodes(self):
        self.assertEqual(cell_format(144,128)['fields']['source_router'],8)
        self.assertLessEqual(cell_format(144,128)['sideband_bits'],64)

    def test_split_cannot_duplicate_compute_budget(self):
        s=vertical_memory()
        with self.assertRaisesRegex(ValueError,'immutable machine budget'):
            replace(s,compute_clusters=(*s.compute_clusters,replace(s.compute_clusters[0],id='free_compute')))


if __name__=='__main__':unittest.main()
