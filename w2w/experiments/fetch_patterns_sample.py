"""Bounded opt-in sample download from one explicitly selected HF mirror folder.

No recursive snapshot, automatic authorization, alternate-host retry or secret
persistence. File choices are the smallest entries in the returned directory page.
"""
import argparse
from hashlib import sha1, sha256
from functools import partial
import json
from pathlib import Path, PurePosixPath
import re
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

REPO = 'core12345/MoE_expert_selection_trace'


class OriginBoundAuthorization(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urlparse(newurl)[:2] != urlparse(req.full_url)[:2]:
            redirected.remove_header('Authorization')
        return redirected


def get_bytes(url, limit, token=None):
    headers = {'User-Agent': 'w2w-trace-input/1.0'}
    if token is not None:
        if urlparse(url).scheme != 'https' or urlparse(url).netloc != 'huggingface.co':
            raise ValueError('Credentials are restricted to the official HF HTTPS host')
        headers['Authorization'] = 'Bearer '+token
    request = Request(url, headers=headers)
    open_url = build_opener(OriginBoundAuthorization()).open if token else urlopen
    try:
        with open_url(request, timeout=30) as response:
            if int(response.headers.get('Content-Length', '0')) > limit:
                raise ValueError('Response exceeds registered byte limit')
            raw = response.read(limit+1)
    except HTTPError as exc:
        detail = exc.read(512).decode(errors='replace')
        reason = 'Cloudflare 1010 client-signature block' if '1010' in detail and 'cloudflare' in exc.headers.get('Server', '').lower() else 'HTTP access rejected'
        if exc.headers.get('X-Error-Code') == 'GatedRepo':
            reason = 'GatedRepo: dataset access authorization required'
        raise RuntimeError(f'HTTP {exc.code}: {reason}; no alternate-host retry') from None
    if len(raw) > limit:
        raise ValueError('Response exceeds registered byte limit')
    return raw


def fetch(endpoint, prefix, output, count=2, max_file_bytes=2*1024**2, max_total_bytes=4*1024**2, token_file=None):
    if urlparse(endpoint).scheme != 'https' or any(v <= 0 for v in (count,max_file_bytes,max_total_bytes)):
        raise ValueError('HTTPS endpoint and positive limits required')
    if not prefix or PurePosixPath(prefix).is_absolute() or '..' in PurePosixPath(prefix).parts:
        raise ValueError('Select one explicit model/benchmark/subject folder')
    read = get_bytes
    if token_file is not None:
        if endpoint.rstrip('/') != 'https://huggingface.co':
            raise ValueError('Token files may only be used with https://huggingface.co')
        token = Path(token_file).read_text().strip()
        if not token.startswith('hf_') or any(c.isspace() for c in token):
            raise ValueError('Token file must contain only one HF token')
        read = partial(get_bytes, token=token)
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be new or empty')
    output.mkdir(parents=True, exist_ok=True)
    receipt = dict(endpoint=endpoint, repository=REPO, prefix=prefix, max_files=count,
                   max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes, downloaded=[])
    try:
        api = endpoint.rstrip('/')+'/api/datasets/'+REPO
        # Default metadata includes a very large siblings list. Request only
        # the pinned revision and gate status, not the entire dataset listing.
        info = json.loads(read(api+'?expand=sha&expand=gated', 8*1024**2))
        revision = info['sha']
        if not re.fullmatch('[a-f0-9]{40}', revision):raise ValueError('Expected immutable dataset commit')
        receipt['revision'] = revision
        if info.get('gated') and token_file is None:
            raise RuntimeError('Dataset reports gated access; obtain authorized local files before import')
        rows = json.loads(read(api+'/tree/'+revision+'/'+quote(prefix,safe='/')+'?limit=1000', 8*1024**2))
        files = sorted((row for row in rows if row['type']=='file' and row['path'].endswith('.json')
                        and 0 < row['size'] <= max_file_bytes), key=lambda row:(row['size'], row['path']))
        receipt['selection_scope'] = 'Smallest files in first nonrecursive directory page, not global dataset minimum'
        chosen, used = [], 0
        for row in files:
            if len(chosen)==count:break
            if used+row['size'] <= max_total_bytes:chosen.append(row);used+=row['size']
        if not chosen:raise ValueError('No JSON files fit limits in this folder')
        for index,row in enumerate(chosen):
            url=endpoint.rstrip('/')+'/datasets/'+REPO+'/resolve/'+revision+'/'+quote(row['path'],safe='/')
            raw=read(url,min(max_file_bytes,max_total_bytes-sum(r['bytes'] for r in receipt['downloaded'])))
            if len(raw)!=row['size']:raise ValueError('Downloaded size differs from metadata')
            value=json.loads(raw)
            if not isinstance(value,list) or not value:raise ValueError('Not a request routing JSON list')
            fingerprint=sha256(raw).hexdigest()
            expected=row.get('lfs',{}).get('oid')
            if expected and expected!=fingerprint:raise ValueError('LFS digest mismatch')
            blob_oid = sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if not expected and row.get('oid') and row['oid'] != blob_oid:
                raise ValueError('Git blob identity mismatch')
            name=f'request{index}.json';(output/name).write_bytes(raw)
            receipt['downloaded'].append(dict(path=name,source_path=row['path'],sha256=fingerprint,
                                             git_blob_oid=blob_oid if not expected else None,bytes=len(raw)))
        manifest=dict(schema='w2w.pbc-files.v1',evidence='captured',
                      source='https://huggingface.co/datasets/'+REPO,revision=revision,
                      requests=[dict(id=r['source_path'],path=r['path'],sha256=r['sha256'],arrival_iteration=0)
                                for r in receipt['downloaded']])
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        receipt['status']='downloaded; layer/model spec still required'
    except Exception as exc:
        receipt['status']='failed';receipt['error']=str(exc)
        raise
    finally:
        (output/'download_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--endpoint',default='https://hf-mirror.com')
    p.add_argument('--prefix',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--max-files',type=int,default=2)
    p.add_argument('--max-file-bytes',type=int,default=2*1024**2)
    p.add_argument('--max-total-bytes',type=int,default=4*1024**2)
    p.add_argument('--token-file',help='Optional secret file; official HF host only; never persisted in receipt')
    args=p.parse_args()
    receipt=fetch(args.endpoint,args.prefix,args.output,args.max_files,args.max_file_bytes,args.max_total_bytes,args.token_file)
    print(json.dumps(receipt))


if __name__=='__main__':main()
