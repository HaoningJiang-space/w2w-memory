"""Reject timing/configuration and landing edits that used to bypass physical cost."""
import json,tempfile,unittest
from pathlib import Path
from dataclasses import replace
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.architecture.presets.recipes import from_recipe


class PhysicalContracts(unittest.TestCase):
    def test_pipeline_and_router_cannot_be_overridden_silently(self):
        s=vertical_memory('central')
        with self.assertRaisesRegex(ValueError,'segment/fine-hop'):
            replace(s,lateral_links=(replace(s.lateral_links[0],channel_cycles=1),*s.lateral_links[1:]))
        changed=tuple(replace(r,cycles=5) for r in s.routers)
        links=tuple(replace(l,channel_cycles=l.channel_cycles-2) for l in s.lateral_links)
        with self.assertRaisesRegex(ValueError,'three-cycle'):
            compile_machine(replace(s,routers=changed,lateral_links=links))

    def test_memory_outline_and_hb_footprint(self):
        s=vertical_memory()
        with self.assertRaisesRegex(ValueError,'footprint'):
            replace(s,vertical_ports=(replace(s.vertical_ports[0],landing_pitch_um=100000),*s.vertical_ports[1:]))
        with self.assertRaisesRegex(ValueError,'registered'):
            replace(s,memory_regions=(replace(s.memory_regions[0],origin_um=(s.memory_regions[0].origin_um[0]+50,s.memory_regions[0].origin_um[1])),*s.memory_regions[1:]))
        regions=tuple(replace(r,origin_um=(r.origin_um[0]+160000,r.origin_um[1])) for r in s.memory_regions)
        domains=tuple(replace(d,position_um=(d.position_um[0]+160000,d.position_um[1])) for d in s.dram_domains)
        with self.assertRaisesRegex(ValueError,'wafer boundary'):
            replace(s,memory_regions=regions,dram_domains=domains,vertical_ports=(),gateways=(),bank_groups=(),collection_paths=())

    def test_recipe_unknown_fields_fail_and_external_lands_are_distinct(self):
        record=json.loads(Path('configs/machine/v3-small.json').read_text());record['gateway_buffer_bytes']=262144
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'recipe.json';p.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'unknown fields'):from_recipe(p,'central')
        ports=vertical_memory('external').external_ports
        self.assertEqual(len({p.position_um for p in ports}),4)
        self.assertEqual(len({p.router_id for p in ports}),4)

    def test_collection_timing_and_pair_identity(self):
        s=vertical_memory('central');path=s.collection_paths[0]
        self.assertGreater(path.minimum_pipeline_cycles,1)
        with self.assertRaisesRegex(ValueError,'Collection timing'):
            replace(s,collection_paths=(replace(path,pipeline_cycles=1),*s.collection_paths[1:]))
        with self.assertRaisesRegex(ValueError,'timing profile'):
            replace(s,collection_paths=(replace(path,timing_profile='free-faster-wire'),*s.collection_paths[1:]))
        with self.assertRaisesRegex(ValueError,'Duplicate collection domain/gateway'):
            replace(s,collection_paths=(*s.collection_paths,replace(path,id=path.id+'-duplicate')))
