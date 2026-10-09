"""One-source native causal intervention: unsupplied A must not block ready B."""
import os,tempfile,unittest
from pathlib import Path
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.backends.booksim.topology_export import compile_booksim
from w2w.backends.booksim.runtime.boundary_booksim import BoundaryBookSim


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY'),'Native binary required')
class ReadyArbiter(unittest.TestCase):
    def test_ready_bypasses_unsupplied_with_one_port(self):
        rows={}
        for ready in (False,True):
            stack=vertical_memory('central');spec=compile_machine(stack)
            with tempfile.TemporaryDirectory() as d:
                nodes,path=compile_booksim(stack.physical_graph,spec,Path(d)/'config')
                client=BoundaryBookSim(Path(os.environ['W2W_BOOKSIM_BINARY']),path,Path(d)/'runtime',flit_bytes=128)
                try:
                    client.configure(rx_slots=256,bounded=True,streaming=True,ready_nodes=(0,) if ready else (),ready_slots=2 if ready else 0)
                    for mid in (0,1):
                        client._request(dict(command='submit',id=mid,cycle=0,source=0,destination=1,flits=4))
                    client._request(dict(command='supply',id=0,cycle=0,flits=1))
                    client._request(dict(command='supply',id=1,cycle=0,flits=4))
                    inject=[]
                    while client.now<16:
                        reply=client._request(dict(command='advance',until=16));client.now=reply['cycle']
                        inject.extend(e for e in reply['progress'] if e['event']=='inject')
                        for e in reply['progress']:
                            if e['event']=='receive':client.commit(e['flit'])
                    rows[ready]=sum(e['id']==1 for e in inject)
                    client._request(dict(command='supply',id=0,cycle=client.now,flits=3))
                    while True:
                        reply=client._request(dict(command='advance',until=client.now+512));client.now=reply['cycle']
                        inject.extend(e for e in reply['progress'] if e['event']=='inject')
                        for e in reply['progress']:
                            if e['event']=='receive':client.commit(e['flit'])
                        if reply['idle']:break
                    self.assertEqual(len({e['cycle'] for e in inject}),8)
                    for mid in (0,1):self.assertEqual([e['ordinal'] for e in inject if e['id']==mid],list(range(4)))
                    client.close()
                except BaseException:
                    client.abort();raise
        self.assertEqual(rows,{False:0,True:4})
