"""Scientific-readback contracts; synthetic records are not hardware evidence."""
import copy,unittest
from tools.read_execution_fabric import mapping_parts,scale_observation


class FabricReadback(unittest.TestCase):
    def test_low_mac_utilization_does_not_imply_unassigned_arrays(self):
        profile=dict(rows=2,columns=2,arrays=4);kernel=dict(M=1,N=4,K=4)
        wave=[dict(M=1,N=2,K=2,m=0,n=n,k=k) for n in (0,2) for k in (0,2)]
        plan=dict(waves=[wave],array_cycles=4,cycles=5,macs=16,mac_utilization=.2,k_partitions=2,program_sha256='fixture')
        result=mapping_parts(kernel,plan,profile)
        self.assertEqual(result['parts']['assigned_array_fraction'],1)
        self.assertEqual(result['parts']['spatial_shape_fraction'],.5)
        self.assertAlmostEqual(result['service_efficiency'],.2)
        bad=copy.deepcopy(plan);bad['mac_utilization']=.4
        with self.assertRaises(ValueError):mapping_parts(kernel,bad,profile)

    def scale_fixture(self):
        key='fixture/gate'
        events=[dict(kind='read_issue',task=key,request='scale',time_ps=0,bytes=128),
            dict(kind='read_deliver',task=key,request='scale',time_ps=1,bytes=128),dict(kind='data_deliver',edge='x',time_ps=2)]
        events.extend(dict(kind='read_issue',task=key,request=f'w{i}',time_ps=i+3,bytes=4096) for i in range(128))
        events.extend(dict(kind='read_deliver',task=key,request=f'w{i}',time_ps=i+203,bytes=4096) for i in range(128))
        return dict(events=events,graph=dict(data=[dict(id='x',consumer=key)]),spec=dict(memory_request_bytes=4096),
            npu_execution=dict(kernels={key:dict(M=1,N=128,K=4096,weight_dtype='FP8_E4M3FN')}))

    def test_scale_storage_tail_is_not_request_issue_tail(self):
        result=scale_observation(self.scale_fixture())
        self.assertEqual(result['cold_expert_kernels'],1);self.assertEqual(result['scale_earlier_than_final_weight'],1)
        self.assertEqual(result['tail_overlap_envelope_ps']['maximum'],328)

    def test_changed_scale_first_contract_is_rejected(self):
        raw=self.scale_fixture();raw['events'][0]['time_ps']=4
        with self.assertRaises(ValueError):scale_observation(raw)


if __name__=='__main__':unittest.main()
