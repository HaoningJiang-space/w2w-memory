"""Complete captured expert-selection traces, separate from simulator events.

No layer substitution, token truncation, synthesized routes or router values.
The public capture contains selected IDs; it is not numerical inference evidence.
"""
import argparse,gzip,hashlib,json
from collections import Counter
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()


def model_shape(config):
    fields=('hidden_size','moe_intermediate_size','num_experts','num_experts_per_tok','num_hidden_layers')
    if any(type(config.get(k)) is not int or config[k]<1 for k in fields):
        raise ValueError('Explicit original model dimensions required')
    if (config.get('model_type')!='qwen3_moe' or config.get('mlp_only_layers')!=[]
            or config.get('decoder_sparse_step')!=1 or config['num_experts_per_tok']>config['num_experts']
            or config.get('quantization_config',{}).get('weight_block_size')!=[128,128]):
        raise ValueError('Only the declared all-layer Qwen3 FP8 capture contract is supported')
    return dict(hidden=config['hidden_size'],intermediate=config['moe_intermediate_size'],
        experts=config['num_experts'],topk=config['num_experts_per_tok'],layers=config['num_hidden_layers'])


def normalize(raw,request,shape):
    layers=[str(i) for i in range(shape['layers'])]
    if not isinstance(raw,list) or len(raw)<2:raise ValueError('Complete prefill and nonempty decode capture required')
    prefill=None;decode={k:[] for k in layers};hist={k:Counter() for k in layers}
    def selection(row):
        if (not isinstance(row,list) or len(row)!=shape['topk']
                or any(type(e) is not int or not 0<=e<shape['experts'] for e in row)
                or len(set(row))!=len(row)):
            raise ValueError('Original unique in-range ranked expert IDs required')
        return row
    for step,record in enumerate(raw):
        if not isinstance(record,dict) or set(record)!=set(layers):raise ValueError('Missing or extra captured layer')
        current={}
        for layer in layers:
            rows=record[layer]
            if not isinstance(rows,list) or not rows:raise ValueError('Empty/null captured routing')
            if step and type(rows[0]) is int:rows=[rows]
            if step and len(rows)!=1:raise ValueError('Decode must contain exactly one captured token')
            current[layer]=[selection(row) for row in rows]
            hist[layer].update(e for row in current[layer] for e in row)
            if step:decode[layer].append(current[layer][0])
        if not step:
            if len({len(v) for v in current.values()})!=1:raise ValueError('Prefill token coverage differs between layers')
            prefill=current
    return dict(schema='w2w.captured-moe-routing.v1',request_id=request['id'],raw_sha256=request['sha256'],
        shape=shape,prefill=prefill,decode=decode,
        coverage=dict(layers=len(layers),prefill_tokens=len(prefill['0']),decode_tokens=len(raw)-1,
            omitted_layers=0,omitted_prefill_tokens=0,omitted_decode_tokens=0,
            expert_assignments=sum(sum(v.values()) for v in hist.values())),
        availability=dict(ranked_expert_ids=True,router_logits=False,router_probabilities=False,
            token_text=False,activation_values=False,arrival_timestamps=False,hardware_events=False),
        scope='Complete original captured expert selections. All layer/token boundaries retained; '
            'no attention/KV/norm/residual timing, mathematical router execution or numerical inference is supplied by this dataset.')


def import_corpus(manifest,config,config_source,output):
    manifest=Path(manifest);config=Path(config);config_source=Path(config_source);output=Path(output)
    m=json.loads(manifest.read_text());s=json.loads(config_source.read_text())
    if (m.get('schema')!='w2w.pbc-files.v1' or m.get('evidence')!='captured'
            or not m.get('revision') or not m.get('requests') or file_sha(config)!=s['sha256']):
        raise ValueError('Hash-bound captured source and pinned model configuration required')
    shape=model_shape(json.loads(config.read_text()));ids=[r['id'] for r in m['requests']]
    if len(set(ids))!=len(ids):raise ValueError('A request cannot be duplicated as independent evidence')
    if any(not k.startswith(s['model']+'/') for k in ids):raise ValueError('Capture and model identities differ')
    output.mkdir(parents=True,exist_ok=False);rows=[];total=Counter()
    for i,request in enumerate(m['requests']):
        source=(manifest.parent/request['path']).resolve()
        if not source.is_relative_to(manifest.parent.resolve()):raise ValueError('Trace path escapes source root')
        if file_sha(source)!=request['sha256']:raise ValueError('Original capture changed')
        normalized=normalize(json.loads(source.read_text()),request,shape)
        target=output/f'request-{i:04d}.json.gz'
        with gzip.open(target,'wt') as f:json.dump(normalized,f,separators=(',',':'))
        coverage=normalized['coverage'];total.update(coverage)
        rows.append(dict(id=request['id'],path=target.name,raw_sha256=request['sha256'],
            normalized_sha256=digest(normalized),file_sha256=file_sha(target),coverage=coverage))
    receipt=dict(schema='w2w.captured-moe-corpus.v1',passed=True,source_commit=revision(),
        dataset_source=m['source'],dataset_revision=m['revision'],source_manifest_sha256=file_sha(manifest),
        model_source=s,shape=shape,requests=rows,total_coverage=dict(total),
        contract='Every manifest request and every original layer/prefill/decode selection imported. '
            'No downsampling, performance selection, padding, repeated request or reused layer route. '
            'Request arrival order/batching are separate execution assumptions, not measured source timing.')
    write_json(output/'manifest.json',receipt)
    return receipt


def verify_corpus(manifest,normalized):
    """Compare every imported entry directly to hashed raw capture, independently of normalization."""
    manifest=Path(manifest);normalized=Path(normalized)
    source=json.loads(manifest.read_text());receipt=json.loads((normalized/'manifest.json').read_text())
    if file_sha(manifest)!=receipt['source_manifest_sha256'] or len(source['requests'])!=len(receipt['requests']):
        raise ValueError('Source request coverage changed')
    assignments=0
    for a,b in zip(source['requests'],receipt['requests']):
        path=manifest.parent/a['path'];out=normalized/b['path']
        if (a['id']!=b['id'] or file_sha(path)!=a['sha256'] or a['sha256']!=b['raw_sha256']
                or file_sha(out)!=b['file_sha256']):raise ValueError('Request identity/hash differs')
        raw=json.loads(path.read_text());r=json.load(gzip.open(out,'rt'))
        if digest(r)!=b['normalized_sha256']:raise ValueError('Normalized routing content changed')
        if (len(raw)-1!=r['coverage']['decode_tokens'] or len(r['decode'])!=receipt['shape']['layers']
                or r['coverage']!=b['coverage']):raise ValueError('Trace truncation detected')
        if raw[0]!=r['prefill']:raise ValueError('Original prefill routing was changed')
        for step,record in enumerate(raw[1:]):
            if set(record)!=set(r['decode']):raise ValueError('Captured layer dropped')
            for layer,value in record.items():
                selected=value[0] if isinstance(value[0],list) else value
                if selected!=r['decode'][layer][step]:raise ValueError('Layer/token routing substituted')
                assignments+=len(selected)
        assignments+=sum(len(row) for rows in r['prefill'].values() for row in rows)
    if assignments!=receipt['total_coverage']['expert_assignments']:raise ValueError('Assignment conservation differs')
    return dict(schema='w2w.captured-moe-coverage-audit.v1',passed=True,analysis_source_commit=revision(),
        source_manifest_sha256=file_sha(manifest),normalized_manifest_sha256=file_sha(normalized/'manifest.json'),
        requests=len(source['requests']),expert_assignments=assignments,compared_every_raw_selection=True,
        scope='Complete capture coverage and source identity, not application execution or numerical validation')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--config',type=Path);p.add_argument('--config-source',type=Path)
    p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:r=verify_corpus(a.manifest,a.output);write_json(a.output/'coverage-audit.json',r)
    else:
        if not a.config or not a.config_source:p.error('Pinned config and source required')
        r=import_corpus(a.manifest,a.config,a.config_source,a.output)
    print(json.dumps(dict(passed=True,requests=len(r['requests']) if isinstance(r['requests'],list) else r['requests'],
        coverage=r.get('total_coverage'),scope=r.get('scope',r.get('contract')))))


if __name__=='__main__':main()
