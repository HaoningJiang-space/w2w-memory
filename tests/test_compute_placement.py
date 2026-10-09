"""Conserve weights/MACs/resources; unified local write work and observed FIFO HOL."""
from collections import Counter
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from w2w.domain.protocol import Packet
from w2w.network.booksim_backend import BookSimNetwork
from w2w.system.builder import SystemBuilder
from w2w.system.wafer_machine import WaferRecipe,from_coordinates
from w2w.workloads.moe_task_graph import compile_layer,machine
from w2w.workloads.moe_partition import compile_partitioned_layer,semantic_work


class PartitionTests(unittest.TestCase):
    def test_static_partition_covers_same_weights_and_macs_on_existing_engines(self):
        base,a=compile_layer(cohort='c2_b4',residency='four_way')
        graph,b=compile_partitioned_layer(cohort='c2_b4')
        self.assertEqual(semantic_work(a),semantic_work(b))
        self.assertEqual(base.objects,graph.objects)
        self.assertEqual(sum(v.get('macs',0) for v in a['task_semantics'].values()),
                         sum(v.get('macs',0) for v in b['task_semantics'].values()))
        self.assertEqual(b['additional_reduction_vector_ops'],393216)
        builder=SystemBuilder(machine()).validate_graph(graph)
        for task in graph.tasks:
            for access in task.reads:
                obj=next(o for o in graph.objects if o.id==access.object_id)
                self.assertEqual(builder.memories[obj.memory].home_tile,task.tile)
        used=Counter(r.object_id for t in graph.tasks for r in t.reads)
        for key in used:
            obj=next(o for o in graph.objects if o.id==key)
            spans=sorted((r.offset_bytes,r.offset_bytes+r.size_bytes) for t in graph.tasks for r in t.reads if r.object_id==key)
            self.assertEqual(spans[0][0],0);self.assertEqual(spans[-1][1],obj.size_bytes)
            self.assertTrue(all(a[1]==b[0] for a,b in zip(spans,spans[1:])))
        self.assertEqual(len(builder.tiles),36)
        self.assertEqual(len(b['all_expert_partition_layout']),512)

    def test_all_expert_content_layout_independent_of_cohort(self):
        _,a=compile_partitioned_layer(cohort='c0_b1')
        _,b=compile_partitioned_layer(cohort='c2_b4')
        self.assertEqual(a['logical_weight_content_layout_sha256'],b['logical_weight_content_layout_sha256'])

    def test_smaller_fields_cannot_be_silently_promoted_to_area_dse(self):
        recipe=WaferRecipe(field_width_um=13000,field_height_um=16500)
        with self.assertRaisesRegex(ValueError,'resource-density'):
            from_coordinates(machine(),recipe)
        _,record=from_coordinates(machine(),recipe,allow_fixed_resource_geometry_sensitivity=True)
        self.assertFalse(record['resource_density']['area_dse_eligible'])


@unittest.skipUnless(os.environ.get('W2W_BOOKSIM_BINARY'),'Instrumented native BookSim required')
class TransportTests(unittest.TestCase):
    def network(self,directory):
        spec=machine()
        return BookSimNetwork(SystemBuilder(spec),[],source=None,binary=os.environ['W2W_BOOKSIM_BINARY'],
                              directory=Path(directory)/'network',local_dma='payload_beats',cell_sideband_bits=64)

    def test_same_local_write_work_for_whole_and_streaming(self):
        for streaming in (False,True):
            with tempfile.TemporaryDirectory() as d:
                network=self.network(d)
                packet=Packet('local/resp','c0','c0','response',4096,())
                self.assertTrue(network.try_send(packet,0,streaming=streaming))
                delivered=[]
                for now in range(0,100_000,1000):
                    network.arrive(now)
                    if streaming and now<=15000:network.supply_prefix(packet.id,(now//1000+1)*256,now)
                    network.deliver(now,lambda p:delivered.append(p.id) or True)
                    if network.drained():break
                self.assertEqual(delivered,[packet.id])
                self.assertEqual(network.rx_write_bytes['c0'],4096)
                self.assertEqual(network.rx_write_cycles['c0'],16)
                self.assertEqual(len(network.cell_tags),1 << 16)
                self.assertFalse(any(network.source_occupied.values()))
                network.close()

    def test_source_hol_counter_observes_ready_message_behind_unsupplied_head(self):
        with tempfile.TemporaryDirectory() as d:
            network=self.network(d)
            route=network.builder.route('c0','c1')
            a=Packet('a/resp','c0','c1','response',512,route)
            b=Packet('b/resp','c0','c1','response',512,route)
            self.assertTrue(network.try_send(a,0,streaming=True))
            network.supply_prefix(a.id,256,0)
            self.assertTrue(network.try_send(b,0))
            for now in range(0,500_000,1000):
                network.arrive(now)
                if now==100_000:network.supply_prefix(a.id,512,now)
                network.deliver(now,lambda p:True)
                if network.drained():break
            network.close()
            p=network.final['source_pressure']
            self.assertGreater(sum(p['ready_behind_unsupplied_cycles']),0)
            self.assertGreater(sum(p['ready_behind_with_injection_credit_cycles']),0)


if __name__=='__main__':unittest.main()
