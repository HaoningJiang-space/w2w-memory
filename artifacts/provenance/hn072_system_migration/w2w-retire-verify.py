import hashlib, json, pathlib, subprocess, tarfile
root=pathlib.Path('/Projects/haoning/w2w-migration-20261009/retired-worktrees')
repo=pathlib.Path('/Projects/haoning/w2w')
manifest=json.loads((root/'manifest.json').read_text())
archive=root/'ignored.tar.gz'
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''): h.update(c)
    return h.hexdigest()
assert digest(archive)==manifest['archive_sha256']
expected={r['name']+'/'+f['path']:f for r in manifest['worktrees'] for f in r['files']}
seen=set()
with tarfile.open(archive,'r:gz') as tar:
    for m in tar:
        assert m.name in expected and m.name not in seen
        seen.add(m.name); e=expected[m.name]
        if e['kind']=='symlink': assert m.issym() and m.linkname==e['target']
        else:
            assert m.isfile() and m.size==e['size']
            h=hashlib.sha256()
            with tar.extractfile(m) as f:
                for c in iter(lambda:f.read(1048576),b''): h.update(c)
            assert h.hexdigest()==e['sha256'],m.name
assert seen==set(expected)
for row in manifest['worktrees']:
    subprocess.run(['git','-C',str(repo),'cat-file','-e',row['commit']+'^{commit}'],check=True)
# Restore one complete archived checkout including ignored files; do not run old experiments.
sample=manifest['worktrees'][-1]
restored=root/'restore-check'
subprocess.run(['git','-C',str(repo),'worktree','add','--detach',str(restored),sample['commit']],check=True)
with tarfile.open(archive,'r:gz') as tar:
    for m in tar:
        prefix=sample['name']+'/'
        if not m.name.startswith(prefix): continue
        relative=pathlib.PurePosixPath(m.name[len(prefix):])
        assert not relative.is_absolute() and '..' not in relative.parts
        dest=restored/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        if m.issym(): dest.symlink_to(m.linkname)
        else: dest.write_bytes(tar.extractfile(m).read())
for f in sample['files']:
    if f['kind']=='file': assert digest(restored/f['path'])==f['sha256']
assert not subprocess.check_output(['git','-C',str(restored),'status','--porcelain']).strip()
receipt=dict(passed=True,archive_sha256=digest(archive),manifest_sha256=digest(root/'manifest.json'),
             files=len(seen),source_commits_available=True,restored_checkout=str(restored),
             destination=str(root),host='ee4e072')
(root/'verified.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
