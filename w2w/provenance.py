"""Environment capture shared by registered experiment entrypoints."""
import subprocess
import platform
import importlib.metadata

def provenance():
    return dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                git_status=subprocess.check_output(['git','status','--porcelain'],text=True),
                host=platform.node(), python=platform.python_version(),
                packages={m:importlib.metadata.version(m) for m in ['numpy','scipy','shapely','pymetis','networkx','matplotlib']})
