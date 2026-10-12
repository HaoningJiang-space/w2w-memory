"""Reject oracle cache/admission as well as early Native reads."""
import copy,unittest
from w2w.validation.route_visibility import audit_route_visibility


class RouteVisibility(unittest.TestCase):
    def test_future_route_is_not_visible_at_cache_lookup_or_admission(self):
        r=dict(runtime_metadata=dict(calls=[dict(layer_id='0',expert_token_counts={'3':2})]),events=[
            dict(kind='task_finish',task='W0000/L0/router_done',time_ps=1000),
            dict(kind='cache_lookup',task='W0000/L0/e3/b0/gate',time_ps=1000),
            dict(kind='task_allocate',task='W0000/L0/e3/pack',time_ps=1000),
            dict(kind='read_issue',task='W0000/L0/e3/b0/gate',time_ps=2000)])
        self.assertEqual(audit_route_visibility(r,0)['checked_route_uses'],3)
        for index in (1,2,3):
            bad=copy.deepcopy(r);bad['events'][index]['time_ps']=999
            with self.assertRaises(ValueError):audit_route_visibility(bad,0)
        bad=copy.deepcopy(r);bad['events'][1]['task']='W0000/L0/t0/dispatch/e3';bad['events'][1]['time_ps']=999
        with self.assertRaises(ValueError):audit_route_visibility(bad,0)


if __name__=='__main__':unittest.main()
