import hashlib, json, pathlib, subprocess, tarfile

base = pathlib.Path('/home/wangziheng/Video')
names = ['w2w-beat-contract-20261008','w2w-cohort-design-20261008',
         'w2w-cohort-replay-20261008','w2w-connectivity-20261008',
         'w2w-provisioning-audit-20261008','w2w-provisioning-holdout-20261008',
         'w2w-provisioning-target-20261008','w2w-return-path-20261008',
         'w2w-system-v2-20261008']
out = pathlib.Path('/tmp/w2w-retire-20261009')
out.mkdir(exist_ok=False)
def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args])
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''): h.update(c)
    return h.hexdigest()
rows=[]
with tarfile.open(out/'ignored.tar.gz','w:gz',compresslevel=6) as tar:
    for name in names:
        root=base/name
        if git(root,'status','--porcelain','--untracked-files=all').strip():
            raise RuntimeError('Not a clean checkout: '+name)
        row=dict(name=name,commit=git(root,'rev-parse','HEAD').decode().strip(),files=[])
        ignored=git(root,'ls-files','--others','--ignored','--exclude-standard','-z').decode().split('\0')
        for relative in filter(None,ignored):
            p=root/relative
            if p.is_symlink(): info=dict(path=relative,kind='symlink',target=p.readlink().as_posix())
            elif p.is_file(): info=dict(path=relative,kind='file',size=p.stat().st_size,sha256=sha(p))
            else: raise RuntimeError('Unexpected ignored entry '+str(p))
            row['files'].append(info)
            tar.add(p,arcname=name+'/'+relative,recursive=False)
        rows.append(row)
manifest=dict(schema='w2w.retirement.v1',source=str(base),worktrees=rows,
              archive_sha256=sha(out/'ignored.tar.gz'))
(out/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(dict(worktrees=len(rows), files=sum(len(r['files']) for r in rows),
                     archive_bytes=(out/'ignored.tar.gz').stat().st_size,
                     archive_sha256=manifest['archive_sha256'])))
