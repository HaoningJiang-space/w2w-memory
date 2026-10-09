#!/usr/bin/env python3
"""Reject active legacy imports and record the current source dependency boundary."""
import ast,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
obsolete=('w2w.geometry','w2w.machine','w2w.network','w2w.memory','w2w.service',
          'w2w.endpoints','w2w.synthesis','w2w.domain.system')
forbidden={'Reticle','Wafer','System','VerticalConnector','rapidchiplet','wafer_sim'}


def audit():
    errors=[];imports={};modules=[]
    for p in sorted((ROOT/'w2w').rglob('*.py')):
        name='.'.join(p.relative_to(ROOT).with_suffix('').parts)
        package=name[:-9] if name.endswith('.__init__') else name.rsplit('.',1)[0]
        tree=ast.parse(p.read_text());entries=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):entries.extend(a.name for a in node.names)
            elif isinstance(node,ast.ImportFrom):
                module=node.module or ''
                if node.level:
                    prefix=package.split('.')[:len(package.split('.'))-node.level+1]
                    module='.'.join((*prefix,*module.split('.'))) if module else '.'.join(prefix)
                entries.append(module)
        for module in entries:
            if module.split('.')[0] in forbidden or module.startswith(obsolete):errors.append([str(p.relative_to(ROOT)),module])
            if module.startswith('w2w.'):
                rel=ROOT/Path(*module.split('.'))
                if not rel.with_suffix('.py').exists() and not (rel/'__init__.py').exists():
                    errors.append([str(p.relative_to(ROOT)),f'missing module {module}'])
        imports[str(p.relative_to(ROOT))]=sorted(set(entries));modules.append(name)
    for filename in ('Reticle.py','Wafer.py','System.py','VerticalConnector.py','run_experiment.py','export_to_rapidchiplet.py'):
        if (ROOT/filename).exists():errors.append([filename,'legacy root source remains'])
    if (ROOT/'rapidchiplet').exists() and any((ROOT/'rapidchiplet').rglob('*.py')):
        errors.append(['rapidchiplet','legacy configuration tree remains'])
    if errors:raise ValueError(json.dumps(errors))
    return dict(schema='w2w.architecture-independence.v3',passed=True,modules=len(modules),imports=imports,
        backend_origins='retained in third_party/booksim_runtime/manifest.json and licenses; not machine architecture sources',
        excluded_owner_directory='rtl/',independent_project='wafer_simulator was not modified')


if __name__=='__main__':print(json.dumps(audit(),indent=2,sort_keys=True))
