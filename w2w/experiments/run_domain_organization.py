"""Non-executable domain specification and a cold whole-matrix falsification foil."""
import argparse,gzip,json,os,time
from pathlib import Path
from dataclasses import asdict
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision

CASES=('up-local','up-local-down-prefetch')


def inputs(case):
    if case not in CASES:raise ValueError('Unknown controlled whole-matrix case')
    from w2w.experiments.run_co_placement import inputs as prior
    from w2w.mapping.down_prefetch import whole_matrix_down_prefetch
    m,g,cache,data=prior('up_local_compute','cold')
    assert cache is None
    plan=whole_matrix_down_prefetch(g) if case==CASES[1] else None
    data=dict(data,down_prefetch_plan=asdict(plan) if plan else None,
        domain_foil_contract='Same current Up-local hardware, complete graph, addresses, two coupled fetch slots and contexts. '
            'Only Down fetch eligibility uses one bounded spare slot; original compute dependencies and full storage retained. '
            '8 B/cluster association charged. Cold-only foil, not executable 128-tile hardware.')
    return m,g,data,plan


def prepare(root):
    from w2w.architecture.domain_compute import domain_compute_specification
    from w2w.mapping.domain_weights import domain_weight_catalog
    from w2w.mapping.data_placement import WeightLocation
    from w2w.workloads.routing_input import load_workload
    from w2w.analysis.domain_organization import domain_organization_bounds
    m,g,data,_=inputs(CASES[0]);logical=load_workload('configs/workloads/c0_b1.json')
    weights=tuple(WeightLocation(**w) for w in data['weights']);spec=domain_compute_specification(m.stack)
    catalog=domain_weight_catalog(logical,m.stack,weights,spec);catalog.pop('slices')
    root.mkdir(parents=True,exist_ok=False);(root/'inputs').mkdir()
    with gzip.open(root/'domain-catalog.json.gz','wt') as f:json.dump(catalog,f)
    write_json(root/'proposal.json',dict(source_commit=revision(),specification=spec.record(),
        catalog_sha256=digest(catalog),logical_catalog_bytes=catalog['logical_catalog_bytes'],
        physical_catalog_bytes=catalog['physical_catalog_bytes'],domain_storage_bytes=catalog['domain_storage_bytes'],
        representative_matrices={p:catalog['matrices']['weight/e0/b0/'+p] for p in ('gate','up','down')},
        bounds=domain_organization_bounds(logical,spec,catalog),
        next_gate='Whole-matrix local computation already exists. Test bounded Down fetch before any 128-tile execution. '
            'A matched 128-tile resolution baseline, local fabric, scale multicast, FIFO/cache and numerical contracts are required for new hardware.'))
    rows={}
    for case in CASES:
        _,_,d,_=inputs(case)
        with gzip.open(root/'inputs'/f'{case}.json.gz','wt') as f:json.dump(d,f)
        rows[case]=dict(input_sha256=digest(d),graph_sha256=digest(d['graph']))
    if len({v['graph_sha256'] for v in rows.values()})!=1:raise ValueError('Mathematics changed')
    write_json(root/'registration.json',dict(schema='w2w.domain-organization-foil.v1',source_commit=revision(),
        cases=rows,max_ps=6000000000,contract='No performance filtering or retries. Shared native tools and exact baseline physical-record check. '
            'Cold foil only; do not promote proposal bounds to simulated domain hardware or cache/energy results.'))


def run(root,case,binary):
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.booksim.adapter import factory
    from w2w.system.kernel import execute_system
    from w2w.validation.vertical_access import audit_vertical_result
    from w2w.validation.request_control import audit_request_control
    from w2w.validation.down_prefetch import audit_down_prefetch
    reg=json.loads((root/'registration.json').read_text());m,g,data,plan=inputs(case)
    if reg['source_commit']!=revision() or reg['cases'][case]['input_sha256']!=digest(data):raise ValueError('Frozen source/input changed')
    directory=root/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    native=VerticalRWDL(m,refresh=True,request_control=True,gateway_trace_bin_ps=1000000);start=time.monotonic()
    try:
        r=execute_system(m,g,native=native,network_factory=factory(binary=binary,directory=directory/'network',
            ready_router_ids=tuple(x.id for x in m.routers),ready_slots=16),time_advance='boundaries',max_ps=reg['max_ps'],
            compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',operand_readiness='contiguous_prefix',
            activation_sram_read_bytes_per_cycle=128,down_prefetch_plan=plan)
        wall=time.monotonic()-start;r['source_commit']=revision();a=audit_vertical_result(r);b=audit_request_control(r)
        c=audit_down_prefetch(r) if plan else None
        if sum(e['macs'] for e in r['events'] if e['kind']=='stream_compute')!=data['metadata']['macs']:
            raise ValueError('Logical arithmetic changed')
        with gzip.open(directory/'result.json.gz','wt') as f:json.dump(r,f)
        write_json(directory/'completion.json',dict(complete=True,source_commit=revision(),input_sha256=digest(data),
            case=case,makespan_ps=r['makespan_ps'],drained_ps=r['drained_ps'],wall_seconds=wall,
            audit=a,control_audit=b,prefetch_audit=c,booksim_sha256=r['network']['identity']['binary_sha256'],
            bridge_sha256=r['native']['bridge_sha256']))
        print(json.dumps(dict(complete=True,case=case,makespan_ps=r['makespan_ps'])),flush=True)
    finally:native.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    actions=p.add_mutually_exclusive_group(required=True);actions.add_argument('--prepare',action='store_true');actions.add_argument('--case',choices=CASES)
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));a=p.parse_args()
    if a.prepare:prepare(a.output)
    else:run(a.output,a.case,a.booksim_binary)
