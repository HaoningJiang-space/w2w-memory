"""Environment capture shared by registered experiment entrypoints."""
import subprocess
import platform
import importlib.metadata

def revision():
    return subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()

def provenance():
    return dict(commit=revision(),
                git_status=subprocess.check_output(['git','status','--porcelain'],text=True),
                host=platform.node(), python=platform.python_version(),
                packages={})
