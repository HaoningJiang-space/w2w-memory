#!/usr/bin/env python3
"""Negative checks on accepted real native records, without a new native run."""
import argparse,copy,gzip,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from w2w.validation.memory_island import audit_memory_island_pair


def check(root):
    if json.loads((root/'VERIFIED.json').read_text()).get('passed') is not True:
        raise ValueError('Accepted positive pair required')
    ref=json.load(gzip.open(root/'run-continuous-0-off/result.json.gz','rt'))
    raw=json.load(gzip.open(root/'run-continuous-0-coordinated/result.json.gz','rt'))
    wakes=json.loads((root/'run-continuous-0-coordinated/wakeups.json').read_text())
    ref_wakes=json.loads((root/'run-continuous-0-off/wakeups.json').read_text())
    positive=audit_memory_island_pair(raw,ref,wakes,ref_wakes)
    mutations={
        'changed_first_ready':lambda r,w:r['events'][next(i for i,e in enumerate(r['events']) if e['kind']=='native_first_ready')].update(time_ps=0),
        'repeated_control_event':lambda r,w:r['events'].append(next(e.copy() for e in r['events'] if e['kind']=='request_control_arrive')),
        'changed_service_credit':lambda r,w:r['native'].update(reservations_live=1),
        'unknown_coordination_field':lambda r,w:r['memory_island'].update(unchecked=True),
        'wrong_internal_tick_total':lambda r,w:r['memory_island'].update(dram_ticks=0),
        'wrong_host_update_total':lambda r,w:r['memory_island'].update(host_advances=1),
        'dropped_noc_wakeup':lambda r,w:(w.remove(1000),r.update(kernel_iterations=len(w)),r['memory_island'].update(host_advances=len(w))),
    }
    rejected=[]
    for name,mutate in mutations.items():
        candidate,changed_wakes=copy.deepcopy(raw),wakes.copy();mutate(candidate,changed_wakes)
        try:audit_memory_island_pair(candidate,ref,changed_wakes,ref_wakes)
        except ValueError:rejected.append(name)
        else:raise ValueError('Accepted corrupted native evidence: '+name)
    return dict(passed=True,positive=positive,rejected=rejected,source='saved native execution; no altered hardware')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();result=check(a.root)
    if a.output.exists():raise ValueError('Fresh negative receipt required')
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
