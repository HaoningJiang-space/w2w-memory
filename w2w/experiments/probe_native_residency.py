"""Two fixed-profile command replays testing native-balanced static residency."""
import argparse
from dataclasses import replace,asdict
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import time

from w2w.analysis.request_window import window_certificate
from w2w.provenance import provenance
from w2w.service.dram.ramulator import RamulatorHBM2
from w2w.service.read_replay import ReadReplayConfig,replay_reads,design_record
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.validation.patterns_replay import check_delivery,check_frozen_accounting
from w2w.workloads.read_trace import ReadTrace,digest

METHOD=Path('docs/methods/NATIVE_MATCHED_RESIDENCY_PROBE.md')
ARCHIVE=Path('artifacts/results/dram/command_bridge')


def run(output):
    prov=provenance()
    if prov['git_status']:
        raise ValueError('Clean source required')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    old_manifest=json.loads((ARCHIVE/'manifest.json').read_text())
    trace=ReadTrace.from_record(old_manifest['selected_trace'])
    if sum(r.size_bytes for t in trace.tasks for r in t.reads)!=18878976 or len(trace.objects)!=128:
        raise ValueError('Full pilot object and population required')
    old_path=ARCHIVE/'b_cfg_hbm2_reference.json.gz'
    old_raw=old_path.read_bytes()
    old=json.loads(gzip.decompress(old_raw))
    catalog=candidate_designs()[0]
    b,wide=catalog['b_cfg'],catalog['wide']
    if any([i for i,v in enumerate(a) if v] != [i for i,v in enumerate(z) if v]
           for a,z in zip(b.layout.shares,wide.layout.shares,strict=True)):
        raise ValueError('Pair support changed')
    balanced=replace(b,name=b.name+'_native_half',layout=wide.layout,home_fraction=Fraction(1,2))
    cfg=ReadReplayConfig(**old['config'])
    result=dict(schema='w2w.native-residency-probe.v1',provenance=prov,
        registration_sha256=sha256(METHOD.read_bytes()).hexdigest(),
        reference_sha256=sha256(old_raw).hexdigest(),trace=trace.record(),trace_sha256=trace.sha256,
        config=asdict(cfg),prediction_time_ratio='13/16',results=[],
        scope='Same HBM2 profile and B endpoint, full single object; residency/static quotas only; not whole workload')
    for label,design in (('original',b),('native_half',balanced)):
        if (design.endpoint!=b.endpoint or design.geometry!=b.geometry or design.exposure!=b.exposure
                or design.shared_directions!=b.shared_directions):
            raise ValueError('Hardware changed')
        start=time.monotonic();backend=RamulatorHBM2(36)
        try:
            row=replay_reads(design,trace,cfg,native_backend=backend)
        finally:
            backend.close()
        if (row['native_backend']['bridge_sha256']!=old['native_backend']['bridge_sha256']
                or row['native_backend']['config_sha256']!=old['native_backend']['config_sha256']):
            raise ValueError('Native binary or profile changed')
        check_delivery(trace,row)
        check_frozen_accounting(window_certificate(design,trace,cfg),row,trace.word_bytes)
        for m,stats in enumerate(row['native_backend']['stats']['controller']):
            words=sum(n for bank,n in row['native_words_by_bank'].items() if int(bank)//32==m)
            if stats['num_read_reqs']!=words or stats['num_read_reqs_served']!=words:
                raise ValueError('Controller differs from required bank words')
        if label=='original' and any(row[k]!=old[k] for k in ('makespan_slots','delivery_sha256','residence_sha256')):
            raise ValueError('Original B no longer reproduces archived service')
        row['wall_seconds']=time.monotonic()-start
        raw=gzip.compress(json.dumps(row,separators=(',',':'),allow_nan=False).encode(),mtime=0)
        path=label+'.json.gz';(output/path).write_bytes(raw)
        result['results'].append(dict(label=label,path=path,sha256=sha256(raw).hexdigest(),
            home_fraction=str(design.home_fraction),makespan_slots=row['makespan_slots'],
            makespan_ns=row['makespan_ns'],design_sha256=digest(design_record(design)),
            delivered_words=row['audit']['delivered_words'],wall_seconds=row['wall_seconds']))
        (output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
        print(label,row['makespan_slots'],row['wall_seconds'],flush=True)
    result['observed_time_ratio']=result['results'][1]['makespan_slots']/result['results'][0]['makespan_slots']
    result['original_matches_archive']=True
    (output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('VERIFIED',result['observed_time_ratio'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    run(p.parse_args().output)
