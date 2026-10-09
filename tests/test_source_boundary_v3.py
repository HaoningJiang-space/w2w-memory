import importlib.util,json,unittest
from pathlib import Path
from dataclasses import replace
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.architecture.serialization import from_record
from w2w.architecture.resources import inventory
from w2w.domain.execution import ResidentObject,ComputeTask,ExecutionGraph
from w2w.system.builder import SystemBuilder


class SourceBoundary(unittest.TestCase):
    def test_current_source_has_no_old_architecture_imports(self):
        p=Path(__file__).resolve().parents[1]/'tools/audit_architecture_independence.py'
        spec=importlib.util.spec_from_file_location('audit_v3',p);module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module);self.assertTrue(module.audit()['passed'])

    def test_physical_record_round_trip(self):
        from dataclasses import asdict
        s=vertical_memory()
        self.assertEqual(asdict(from_record(json.loads(json.dumps(asdict(s))))),asdict(s))

    def test_native_views_cannot_clone_resident_capacity(self):
        s=vertical_memory();group=s.bank_groups[0];alias=replace(group,id='alias')
        spec=compile_machine(replace(s,bank_groups=(*s.bank_groups,alias)))
        a=ResidentObject('a',group.id,0,4096)
        b=ResidentObject('b','alias',0,4096)
        graph=ExecutionGraph((ComputeTask('t','c0',0),),(a,b))
        with self.assertRaisesRegex(ValueError,'content overlaps'):SystemBuilder(spec).validate_graph(graph)
        a=replace(a,storage_id='shared');b=replace(b,storage_id='shared')
        SystemBuilder(spec).validate_graph(replace(graph,objects=(a,b)))
        self.assertEqual(inventory(spec.stack)['native']['capacity_bytes'],8*1024**3)


if __name__=='__main__':unittest.main()
