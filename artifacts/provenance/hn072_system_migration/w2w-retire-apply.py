import hashlib, json, os, pathlib, shutil, subprocess
root=pathlib.Path('/tmp/w2w-retire-20261009')
manifest=json.loads((root/'manifest.json').read_text())
verified=json.loads((root/'verified.json').read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''):h.update(c)
    return h.hexdigest()
assert verified['passed'] and verified['host']=='ee4e072'
assert verified['manifest_sha256']==sha(root/'manifest.json')
assert verified['archive_sha256']==manifest['archive_sha256']
base=pathlib.Path(manifest['source'])
assert str(base)=='/home/wangziheng/Video'
paths=[base/r['name'] for r in manifest['worktrees']]
assert len(paths)==9 and all(p.name.startswith('w2w-') for p in paths)
def git(p,*args):return subprocess.check_output(['git','-C',str(p),*args])
for r,p in zip(manifest['worktrees'],paths):
    assert git(p,'rev-parse','HEAD').decode().strip()==r['commit']
    assert not git(p,'status','--porcelain','--untracked-files=all').strip()
    actual=set(filter(None,git(p,'ls-files','--others','--ignored','--exclude-standard','-z').decode().split('\0')))
    assert actual=={f['path'] for f in r['files']}
    for f in r['files']:
        path=p/f['path']
        if f['kind']=='file':assert sha(path)==f['sha256'],str(path)
        else:assert path.is_symlink() and os.readlink(path)==f['target']
protected=[]
for proc in pathlib.Path('/proc').iterdir():
    if not proc.name.isdigit():continue
    try:
        if proc.stat().st_uid!=os.getuid():continue
        comm=(proc/'comm').read_text().strip()
        refs=[proc/'cwd',proc/'exe',*list((proc/'fd').iterdir())]
        for ref in refs:
            try:target=os.readlink(ref)
            except FileNotFoundError:continue
            assert not any(target==str(p) or target.startswith(str(p)+'/') for p in paths),(str(ref),target)
        maps=(proc/'maps').read_text()
        assert not any(str(p)+'/' in maps for p in paths),str(proc)
    except FileNotFoundError:continue
    except PermissionError:
        assert comm in ('sshd','(sd-pam)','systemd'),(str(proc),comm)
        protected.append(dict(pid=proc.name,comm=comm))
before=shutil.disk_usage(base).free
for p in paths:
    subprocess.run(['git','-C',str(base/'w2w-provisioning-20261008'),
                    'worktree','remove','--force',str(p)],check=True)
os.sync()
after=shutil.disk_usage(base).free
receipt=dict(retired=True,removed=[str(p) for p in paths],destination=verified,
             free_bytes_before=before,free_bytes_after=after,observed_free_bytes_change=after-before,
             source_rechecked=True,uninspectable_service_processes=protected,
             preserved=['primary repositories','other W2W worktrees','environments','wafer_simulator','other projects'])
(root/'retired.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
