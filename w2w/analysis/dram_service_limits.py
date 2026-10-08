"""Read archived command-model evidence and expose native service constraints.

No new DRAM run, timing calibration or conversion of HBM bandwidth into WoW
bandwidth. Profiles with different native organizations remain separate.
"""
import argparse
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.provenance import provenance


def required_inflight(rate_bytes_per_ns, minimum_latency_ns, burst_bytes):
    """Necessary count from conservation; queueing and return latency add more."""
    q=Fraction(str(rate_bytes_per_ns))*Fraction(str(minimum_latency_ns))/burst_bytes
    if q<0 or burst_bytes<=0:
        raise ValueError('Nonnegative rate/latency and positive burst required')
    return (q.numerator+q.denominator-1)//q.denominator


def analyze(source):
    source=Path(source)
    manifest=json.loads((source/'manifest.json').read_text())
    rows=[]
    for item in manifest['results']:
        if item['kind']!='hbm2_reference':
            continue
        raw=(source/item['path']).read_bytes()
        if sha256(raw).hexdigest()!=item['sha256']:
            raise ValueError('Archived command evidence changed')
        row=json.loads(gzip.decompress(raw))
        native=row['native_backend']
        controllers=native['config']['memory_system']['controllers']
        if len(controllers)!=36 or native['upstream_commit']!='72427a1bba3771564c4fb0e494ba02242fd1eaa7':
            raise ValueError('Unregistered native organization')
        dram=controllers[0]['dram']
        if any(c['dram']!=dram for c in controllers):
            raise ValueError('Reference channels differ')
        burst=dram['data_payload_bytes']
        # Explicit indices in the pinned resolved HBM2 timing array: rate, nBL.
        rate_mbps,nbl=dram['timing'][:2]
        tck_ns=Fraction(native['tck_ps'],1000)
        peak=Fraction(dram['org']['count'][1]*burst,nbl)/tck_ns
        dq_peak=Fraction(dram['channel_width']*rate_mbps,8000)
        if peak!=dq_peak:
            raise ValueError('DQ rate disagrees with burst service bound')
        min_latency=dram['read_latency']*tck_ns
        active=[]
        for m,stats in enumerate(native['stats']['controller']):
            words=sum(n for bank,n in row['native_words_by_bank'].items() if int(bank)//32==m)
            if not words:
                continue
            if stats['num_read_reqs_served']!=words or stats['num_read_reqs']!=words:
                raise ValueError('Native words differ from frozen bank traffic')
            actual=Fraction(words*burst)/Fraction(str(row['makespan_ns']))
            if actual>peak:
                raise ValueError('Archived service exceeds native bus bound')
            active.append(dict(memory=m,words=words,effective_GB_s=float(actual),
                fraction_of_channel_peak=float(actual/peak),read_row_hits=stats['read_row_hits'],
                read_row_conflicts=stats['read_row_conflicts'],read_row_misses=stats['read_row_misses'],
                row_hit_fraction=stats['read_row_hits']/words,
                mean_controller_latency_ns=stats['avg_read_latency']*float(tck_ns)))
        rows.append(dict(path=item['path'],sha256=item['sha256'],design_name=row['design']['name'],
            burst_bytes=burst,banks_per_memory=32,independent_pseudochannels=dram['org']['count'][1],
            native_channel_peak_GB_s=float(peak),minimum_read_latency_ns=float(min_latency),
            minimum_native_inflight_at_peak=required_inflight(peak,min_latency,burst),
            old_slot_native_GB_s_per_memory=1000.,active_memories=active,
            source_depths=row['design']['endpoint']['depths'],
            outstanding_words_per_compute=row['config']['outstanding_words_per_compute']))
    if len(rows)!=4:
        raise ValueError('Expected four native reference replays')
    return dict(schema='w2w.dram-service-limits.v1',provenance=provenance(),profiles=rows,
        conditional_example=dict(target_GB_s=1000,minimum_latency_ns=16,burst_bytes=32,
            minimum_inflight=required_inflight(1000,16,32),
            scope='Conditional conservation example, not a modified or calibrated HBM/WoW profile'),
        scope='Reanalysis of archived native data; no new simulation or common-budget comparison across profiles')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',default='artifacts/results/dram/command_bridge');p.add_argument('--output',required=True)
    a=p.parse_args();result=analyze(a.source)
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
    print('VERIFIED',len(result['profiles']),'archived native profiles; no new simulation')
