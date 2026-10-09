"""Export physical machine, resource inventory and native network without executing."""
import argparse,json
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory
from w2w.backends.booksim import compile_booksim
from w2w.common.io import write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=Path('configs/machine/v3-small.json'))
    p.add_argument('--organization',choices=('central','distributed','external'),default='distributed')
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    stack=from_recipe(args.config,args.organization);spec=compile_machine(stack)
    write_json(args.output/'machine.json',asdict(stack));write_json(args.output/'resources.json',inventory(stack))
    compile_booksim(stack.physical_graph,spec,args.output/'network')
    print(json.dumps(dict(machine=stack.name,clusters=len(stack.compute_clusters),routers=len(stack.routers),
        domains=len(stack.dram_domains),ports=len(stack.vertical_ports))))


if __name__=='__main__':main()
