"""Direct physical graph -> AnyNet/config. No chiplet or placement dictionaries."""
from pathlib import Path
import json


def compile_booksim(graph, policy, output_directory):
    root=Path(output_directory).resolve()
    root.mkdir(parents=True,exist_ok=True)
    nodes={r.id:i for i,r in enumerate(graph.routers)}
    if len(nodes)!=len(graph.routers): raise ValueError('Duplicate physical router')
    rows=[]
    for key,n in nodes.items():
        row=f'router {n} node {n} 1'
        for link in graph.channels:
            if link.src==key:
                if link.dst not in nodes or link.credit_cycles!=link.pipeline_cycles:
                    raise ValueError('Native channel requires explicit endpoints and equal data/credit latency')
                row+=f' router {nodes[link.dst]} {link.pipeline_cycles}'
        rows.append(row)
    (root/'network.anynet').write_text('\n'.join(rows)+'\n')
    (root/'empty_network_input.json').write_text('[]\n')
    cycles=policy.router_cycles
    config=dict(topology='anynet',network_file=str(root/'network.anynet'),mode='trace',
        trace_file=str(root/'empty_network_input.json'),trace_report=str(root/'trace_report.json'),
        trace_skip_idle=0,seed=1,ignore_cycles=0,sim_count=1,trace_time_out=60,
        warmup_periods=0,sample_period=1000000000,traffic='uniform',packet_size=1,
        num_vcs=1,vc_buf_size=policy.input_buffer_flits,wait_for_tail_credit=0,
        injection_rate=1.0,injection_rate_uses_flits=1,deadlock_warn_timeout=200000,
        credit_delay=0,routing_delay=0,vc_alloc_delay=1,sw_alloc_delay=1,
        st_final_delay=max(1,cycles-2),input_speedup=1,output_speedup=1,
        internal_speedup=1.0 if cycles>=3 else 3.0/cycles,use_read_write=0,
        routing_function='modular_routing',modular_routing_function='simple_cycle_breaking_set',
        modular_selection_function='adaptive',path_for_stats=str(root/'network_stats.csv'),
        path_for_xy_info=str(root/'network_xy.csv'))
    path=root/'network.conf'
    path.write_text(''.join(f'{key} = {value};\n' for key,value in config.items()))
    (root/'topology_identity.json').write_text(json.dumps(dict(
        nodes=nodes,channels=[dict(id=l.id,src=l.src,dst=l.dst,cycles=l.pipeline_cycles) for l in graph.channels],
        policy='native cycle-breaking adaptive; planned frontend route is only a legal route',
        physical_paths='actual execution paths are taken from native link-arrival records'),indent=2)+'\n')
    return nodes,path
