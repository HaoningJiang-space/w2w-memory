"""Reconstruct static-binding control metrics from archived mapping and replay."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[2]


def audit():
    folder=ROOT/'artifacts/provenance/static_binding'
    manifest=json.loads((ROOT/'artifacts/results/endpoint/static_binding/manifest.json').read_text())
    receipt=json.loads((folder/'static_binding_evidence.json').read_text())
    archive=folder/'static_binding_evidence.tar.gz'
    if sha256(archive.read_bytes()).hexdigest()!=receipt['archive_sha256']:
        raise ValueError('Archive hash mismatch')
    with tarfile.open(archive,'r:gz') as tar:
        members={m.name:m for m in tar.getmembers()}
        if set(members)!=set(receipt['files']) or not all(m.isfile() for m in members.values()):
            raise ValueError('Unexpected archive contents')
        contents={name:tar.extractfile(member).read() for name,member in members.items()}
    if any(sha256(contents[p]).hexdigest()!=h for p,h in receipt['files'].items()):
        raise ValueError('Evidence file hash mismatch')
    if json.loads(contents['manifest.json'])!=manifest or not manifest['complete']:
        raise ValueError('Manifest incomplete or changed')
    for path, h in manifest['rtl_sha256'].items():
        if sha256((ROOT/path).read_bytes()).hexdigest()!=h: raise ValueError('RTL changed')
    reference=ROOT/'artifacts/results/endpoint/endpoint_roundtrip.json.gz'
    if sha256(reference.read_bytes()).hexdigest()!=manifest['trace_archive_sha256']:
        raise ValueError('Reference trace changed')
    records={f"{r['pattern']}_dir{r['direction']}":r for r in json.loads(gzip.decompress(reference.read_bytes()))['records'] if r['width']==160}
    physical=ROOT/'artifacts/results/endpoint/endpoint_physical_slice.json.gz'
    mapped_reference={r['case']:r['result'] for r in
        json.loads(gzip.decompress(physical.read_bytes()))['manifest']['simulation']['mapped_zero_delay']}
    names={'duplicated','configurable','pruned_dup_l','pruned_dup_r','pruned_cfg_l','pruned_cfg_r'}
    if set(manifest['blocks'])!=names: raise ValueError('Missing mapping control')
    for name,b in manifest['blocks'].items():
        raw=contents[f'{name}/stat.json']
        if sha256(raw).hexdigest()!=b['stat_sha256'] or sha256(contents[f'{name}/netlist.v']).hexdigest()!=b['netlist_sha256']:
            raise ValueError('Mapping identity mismatch')
        stat=json.loads(raw)['modules']['\\mapped_'+name]
        counts={k:v for k,v in stat['num_cells_by_type'].items() if k!='$scopeinfo'}
        if counts!=b['cells'] or stat['area']!=b['area_um2'] or sum(v for c,v in counts.items() if c.startswith(('DFF','SDFF')))!=b['sequential_cells']:
            raise ValueError('Mapped area or state count mismatch')
    if set(manifest['simulations'])!=names-{'duplicated','configurable'}:
        raise ValueError('Missing mapped simulation')
    words=cycles=cases=0
    for name,rows in manifest['simulations'].items():
        direction=0 if name.endswith('_l') else 1
        expected_cases={k for k,r in records.items() if r['direction']==direction}
        if len(rows)!=7 or {r['case'] for r in rows}!=expected_cases:
            raise ValueError('Missing direction/traffic case')
        for row in rows:
            r=records[row['case']]
            # The RTL bench waits eight quiet drain cycles; the original Python
            # fixture ends on delivery. Compare cycles to the archived RTL bench.
            expected=[mapped_reference[row['case']][0],r['accepted'],*r['received'],*r['measured_received'],r['measured_accepted'],r['source_stall_cycles'],r['hb_stall_port_cycles'],r['rx_stall_port_cycles']]
            if row['result'][:12]!=expected: raise ValueError('Frozen cycle/service mismatch')
            if row['result']!=mapped_reference[row['case']]: raise ValueError('Archived mapped replay mismatch')
            line=next(s for s in contents[f'{name}/{row["case"]}.log'].decode().splitlines() if s.startswith('RESULT '))
            if list(map(int,line.split()[1:]))!=row['result']: raise ValueError('Replay log mismatch')
            words+=r['accepted'];cycles+=row['result'][0];cases+=1
    return dict(schema='w2w.static-binding-audit.v1',source_commit=manifest['source_commit'],
                mapped_blocks=6,paired_cases=cases,paired_cycles=cycles,words_per_side=words,
                stat_cells_and_area_reconstructed=True,frozen_service_and_logs_equal=True,
                reference_mapped_archive_sha256=sha256(physical.read_bytes()).hexdigest(),
                scope='Matched library mapping and zero-delay mapped payload replay; not physical timing closure')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();result=audit();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
