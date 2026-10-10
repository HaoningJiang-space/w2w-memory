"""Sparse event analysis must separate prefix holes from shared-service waiting."""
import unittest
from w2w.analysis.ffn_stages import stages


class StageEvents(unittest.TestCase):
    def record(self,events,finish,busy):
        return dict(graph=dict(tasks=[dict(id='e0/b0/gate',tile='c0',release_ps=0,stream=dict(weight_data_bytes=128))],data=[],control=[]),
            spec=dict(stack=dict(compute_clusters=[dict(id='c0',profile=dict(period_ps=1000))])),
            events=[dict(task='e0/b0/gate',**e) for e in events],
            tasks={'e0/b0/gate':dict(start_ps=0,finish_ps=finish)},compute_busy_ps={'c0':busy})

    def test_prefix_hole_and_ungranted_ready_clock(self):
        events=[dict(kind='task_allocate',time_ps=0),
            dict(kind='read_issue',time_ps=0,request='r128'),dict(kind='read_issue',time_ps=0,request='r64'),dict(kind='read_issue',time_ps=0,request='r0'),
            dict(kind='stream_operand_ready',time_ps=0,object_offset=128,bytes=32,request='r128'),
            dict(kind='task_start',time_ps=0),dict(kind='stream_compute',time_ps=0,weight_bytes=0),
            dict(kind='stream_operand_ready',time_ps=1500,object_offset=64,bytes=64,request='r64'),
            dict(kind='stream_operand_ready',time_ps=2500,object_offset=0,bytes=64,request='r0'),
            dict(kind='stream_compute',time_ps=3000,weight_bytes=64),
            dict(kind='stream_compute',time_ps=5000,weight_bytes=64),dict(kind='task_finish',time_ps=6000)]
        row=stages(self.record(events,6000,3000))['tasks']['e0/b0/gate']
        self.assertEqual(row['operand_wait_ps'],2000)
        self.assertEqual(row['ready_service_wait_ps'],1000)
        self.assertEqual(row['busy_ps'],3000)

    def test_cached_operands_have_no_memory_wait(self):
        events=[dict(kind='task_allocate',time_ps=0),dict(kind='cache_operands_ready',time_ps=0),
            dict(kind='task_start',time_ps=0),dict(kind='stream_compute',time_ps=0,weight_bytes=0),
            dict(kind='stream_compute',time_ps=1000,weight_bytes=128),dict(kind='task_finish',time_ps=2000)]
        row=stages(self.record(events,2000,2000))['tasks']['e0/b0/gate']
        self.assertEqual(row['operand_wait_ps'],0);self.assertEqual(row['ready_service_wait_ps'],0)


if __name__=='__main__':unittest.main()
