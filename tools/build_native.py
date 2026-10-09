#!/usr/bin/env python3
"""Build native system tools from this checkout into a new external directory.

BookSim base, changes, IPC and JSON headers are in this Git repository.
Unmodified Ramulator is a pinned dependency; all W2W bridge changes are here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT/'third_party/booksim_runtime'
RAMULATOR_PIN = '72427a1bba3771564c4fb0e494ba02242fd1eaa7'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--tool', choices=('booksim','dram','all'), default='all')
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--ramulator-source', type=Path,
                   help='Reuse a built pinned upstream; otherwise clone/build into output')
    args = p.parse_args()
    required = ['cmake','g++','git']
    if args.tool in ('booksim','all'): required += ['make','flex','bison']
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        p.error('Missing build tools: '+', '.join(missing))
    out = args.output.resolve()
    if out == ROOT or ROOT in out.parents or args.jobs < 1:
        p.error('Use a new build directory outside the source checkout and positive --jobs')
    out.mkdir(parents=True, exist_ok=False)
    commands = []
    with (out/'build.log').open('w') as log:
        def run(cmd, cwd=ROOT):
            cmd = [str(s) for s in cmd]
            commands.append(dict(argv=cmd, cwd=str(cwd)))
            log.write(json.dumps(commands[-1])+'\n'); log.flush()
            subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)

        manifest = dict(schema='w2w.native-build.v1', host=platform.node(),
                        python=sys.version, commands=commands, outputs={}, sources={})
        manifest['tools'] = {name: shutil.which(name) for name in required}
        manifest['w2w_commit'] = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        try:
            if args.tool in ('booksim','all'):
                inputs = json.loads((VENDOR/'manifest.json').read_text())
                for name, expected in inputs['base_sha256'].items():
                    if digest(ROOT/name) != expected:
                        raise ValueError(f'Changed historical BookSim base: {name}')
                required = [ROOT/name for name in inputs['base_sha256']]
                required += [p for p in VENDOR.rglob('*') if p.is_file()]
                required += list((ROOT/'w2w/backends/booksim/runtime').glob('*.py'))
                manifest['sources'].update({str(p.relative_to(ROOT)):digest(p) for p in required})
                build = out/'booksim'
                native = build/'third_party/booksim2/src'
                shutil.copytree(ROOT/'third_party/booksim2',build/'third_party/booksim2')
                for patch in ('booksim-wafer.patch','booksim-endpoint-hooks.patch'):
                    run(['git','apply','--check',VENDOR/patch],build)
                    run(['git','apply',VENDOR/patch],build)
                includes = ['-I'+str(native/path) for path in ('','allocators','arbiters','routers','networks','power')]
                includes.append('-I'+str(VENDOR/'include'))
                run(['make','-C',native,f'-j{args.jobs}','CXX=g++ -I'+str(VENDOR/'include')])
                run(['g++','-std=c++17','-O3',*includes,'-Dmain=unused_booksim_main','-c',native/'main.cpp','-o',build/'globals.o'])
                run(['g++','-std=c++17','-O3','-Wall',*includes,'-DWAFER_ENDPOINT_BOUNDARY','-c',VENDOR/'native/online_booksim.cpp','-o',build/'online.o'])
                objects = sorted(p for p in native.rglob('*.o') if p.name != 'main.o')
                binary = build/'endpoint_booksim'
                run(['g++','-std=c++17','-O3',build/'online.o',build/'globals.o',*objects,'-o',binary])
                manifest['outputs']['booksim'] = dict(path=str(binary),sha256=digest(binary))
            if args.tool in ('dram','all'):
                if args.ramulator_source:
                    dram = args.ramulator_source.resolve()
                else:
                    dram = out/'ramulator2'
                    run(['git','clone','https://github.com/CMU-SAFARI/ramulator2.git',dram])
                    run(['git','checkout','--detach',RAMULATOR_PIN],dram)
                    run(['cmake','-S',dram,'-B',dram/'build',f'-DPython_EXECUTABLE={sys.executable}','-DCMAKE_BUILD_TYPE=Release'])
                    run(['cmake','--build',dram/'build',f'-j{args.jobs}'])
                revision = subprocess.check_output(['git','-C',str(dram),'rev-parse','HEAD'],text=True).strip()
                if revision != RAMULATOR_PIN:
                    raise ValueError('Ramulator must use the registered upstream commit')
                manifest['ramulator'] = dict(commit=revision,path=str(dram),library_sha256=digest(dram/'libramulator.so'))
                for path in (ROOT/'w2w/backends/ramulator').glob('*'):
                    if path.is_file(): manifest['sources'][str(path.relative_to(ROOT))]=digest(path)
                run(['cmake','-S',ROOT/'w2w/backends/ramulator','-B',out/'dram_bridge',f'-DRAMULATOR_SOURCE={dram}',f'-DPython_EXECUTABLE={sys.executable}'])
                run(['cmake','--build',out/'dram_bridge',f'-j{args.jobs}'])
                bridge, = (out/'dram_bridge').glob('_w2w_ramulator*.so')
                manifest['outputs']['dram_bridge'] = dict(path=str(bridge),sha256=digest(bridge))
            manifest['complete'] = True
            manifest['compiler'] = subprocess.check_output(['g++','--version'],text=True)
        finally:
            (out/'build-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps(manifest['outputs'],indent=2))


if __name__ == '__main__': main()
