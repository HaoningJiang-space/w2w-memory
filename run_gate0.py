"""Recompute all Table 1 topologies; retain upstream conventions for audit."""
import argparse
import json
from pathlib import Path
import random
import subprocess
import platform
import importlib.metadata
import numpy as np
import analyze_topology as at
import config
from run_experiment import construct_system_for_single_design

# Table 1, https://arxiv.org/html/2603.05266v1 (counts, C/I radix, diameter, mean, cut)
TABLE = [
 ('logic_and_interconnect',200,'rectangular',[(20,26,4,4,8,4.08,16),(20,10,4,6,6,3.30,16),(20,12,4,6,8,3.44,16),(20,20,7,7,6,2.84,32)]),
 ('logic_and_interconnect',200,'maximized',[(26,26,4,4,12,4.80,16),(26,12,4,6,10,3.91,16.4),(26,14,4,6,10,3.89,16),(27,25,7,7,6,3.20,38)]),
 ('logic_and_interconnect',300,'rectangular',[(49,56,4,4,12,6.44,27.2),(49,28,4,6,12,5.53,28),(49,26,4,6,12,5.57,24),(48,48,7,7,10,4.19,47.6)]),
 ('logic_and_interconnect',300,'maximized',[(64,63,4,4,18,7.45,26),(64,31,4,6,14,5.83,31.2),(64,31,4,6,14,6.04,28.2),(66,63,7,7,10,4.76,64.2)]),
 ('logic_and_logic',200,'rectangular',[(46,0,4,None,10,4.40,16),(40,0,5,None,8,3.52,16)]),
 ('logic_and_logic',200,'maximized',[(52,0,4,None,12,4.71,16),(54,0,5,None,10,3.93,21.2)]),
 ('logic_and_logic',300,'rectangular',[(105,0,4,None,14,6.66,27.2),(96,0,5,None,12,5.20,28)]),
 ('logic_and_logic',300,'maximized',[(127,0,4,None,20,7.42,25.6),(132,0,5,None,16,6.01,36)])]


def provenance():
    return dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                git_status=subprocess.check_output(['git','status','--porcelain'],text=True),
                host=platform.node(), python=platform.python_version(),
                packages={m:importlib.metadata.version(m) for m in ['numpy','scipy','shapely','pymetis','networkx','matplotlib']})


def run(output, seed):
    rows=[]
    for integration,diameter,util,expected in TABLE:
        for method,exp in zip(['baseline','ours_aligned','ours_interleaved','ours_rotated'],expected):
            d=dict(integration_level=integration,wafer_diameter=diameter,wafer_utilization=util,
                   method=method,routing_function='simple_cycle_breaking_set',selection_function='random',traffic='uniform')
            system=construct_system_for_single_design(d,config.parameters)
            random.seed(seed)
            measured=at.analyze_topology(system)
            cs=[r.attributes['n_neighbors'] for w in system.wafers for r in w.reticles if r.typ=='compute']
            ins=[r.attributes['n_neighbors'] for w in system.wafers for r in w.reticles if r.typ=='interconnect']
            values=[measured['n_compute_reticles'],measured['n_interconnect_reticles'],max(cs),max(ins) if ins else None,
                    measured['diameter'],round(measured['path_length_mean'],2),measured['bisection_bandwidth_mean']]
            adj=at.extract_adjacency_list(system)
            simple=[sorted(set(neighbors)) for neighbors in adj]
            random.seed(seed)
            cut=at.estimate_bisection_bandwidth(simple)
            row=dict(design=d,expected=list(exp),measured=values,deterministic_match=values[:6]==list(exp[:6]),
                     counts_diameter_hops_match=values[:2]+values[4:6]==list(exp[:2])+list(exp[4:6]),
                     bisection_delta=values[6]-exp[6],bisection_std=measured['bisection_bandwidth_std'],
                     unique_link_cut_mean=cut[0],unique_link_cut_std=cut[1],
                     unique_link_bisection_tb_s=cut[0]*config.link_bandwidth_bit_per_sec/8/1e12,
                     duplicated_adjacency_entries=sum(map(len,adj))-sum(map(len,simple)))
            rows.append(row)
            print(integration,diameter,util,method,'match',row['deterministic_match'],'cut_delta',row['bisection_delta'],flush=True)
            Path(output).write_text(json.dumps(dict(provenance=provenance(),seed=seed,rows=rows),indent=2))
    if not all(r['counts_diameter_hops_match'] for r in rows):
        raise SystemExit('Table 1 counts/diameter/hops mismatch; inspect results')
    print('Actual degree differs from nominal Table 1 radix in',
          sum(not r['deterministic_match'] for r in rows),'rows',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',default='memory_results/gate0.json');p.add_argument('--seed',type=int,default=20261006)
    a=p.parse_args();Path(a.output).parent.mkdir(parents=True,exist_ok=True);run(a.output,a.seed)
