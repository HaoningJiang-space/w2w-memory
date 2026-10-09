#!/usr/bin/env python3
"""One-domain native row examples; no NoC/CDC/compute and no refresh in these examples."""
import argparse,json
from pathlib import Path
from w2w.service.dram.rwdl import RamulatorRWDL


def sample(addresses):
    native=RamulatorRWDL(1,refresh=False);ready={};next_atom=0;peak=0
    try:
        for cycle in range(10000):
            ready.update(native.advance(cycle*3760))
            if next_atom<len(addresses) and native.submit(0,addresses[next_atom]) is not None:next_atom+=1
            peak=max(peak,len(native.pending))
            if len(ready)==len(addresses):break
        if len(ready)!=len(addresses) or peak>8:raise RuntimeError('Example failed to drain within the declared native reservation scale')
        return dict(first_callback_cycle=ready[0],last_callback_cycle=ready[len(addresses)-1],
            row_start_callback_cycles=[ready[i] for i in range(0,len(addresses),64)],
            atoms=len(addresses),peak_native_live_atoms=peak,stats=native.record()['stats']['controller'][0],
            native_identity={k:native.record()[k] for k in ('upstream_commit','bridge_sha256','config_sha256')})
    finally:native.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    hit=sample([i%64 for i in range(128)]);rows=sample(list(range(1024)))
    gaps=[b-a for a,b in zip(rows['row_start_callback_cycles'],rows['row_start_callback_cycles'][1:])]
    if set(gaps)!={73} or hit['last_callback_cycle']-hit['first_callback_cycle']!=127:raise ValueError('Native examples differ from candidate timings')
    value=dict(scope='native one-array examples, read queue one, no refresh; 32-domain rate is an analytical projection',
        row_hit=hit,row_stream=rows,observed_row_start_intervals_cycles=gaps,
        projected_interface_peak_GBps=32*16*1000/3760,
        projected_row_stream_GBps=32*64*16*1000/(73*3760),
        row_stream_reference_us_for_28318464_bytes=28318464/(32*64*16*1000/(73*3760))/1000)
    args.output.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({k:v for k,v in value.items() if k not in ('row_hit','row_stream')}))


if __name__=='__main__':main()
