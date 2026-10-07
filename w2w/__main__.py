"""Usage: python -m w2w COMMAND [arguments]."""
import argparse
import runpy
import sys
from w2w.commands import COMMANDS


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help', '--list'):
        print('Usage: python -m w2w COMMAND [arguments]\n')
        print('Commands (original script names, without .py):')
        for group in ('experiments', 'endpoints', 'analysis', 'validation', 'visualization'):
            print('\n  '+group+':')
            for name,module in COMMANDS.items():
                if module.split('.')[1] == group: print('    '+name)
        print('\nTests: python -m unittest discover -s tests -v')
        return
    command = argv.pop(0).removesuffix('.py')
    if command not in COMMANDS:
        parser=argparse.ArgumentParser(prog='python -m w2w')
        parser.error('unknown command '+repr(command)+'; use --list')
    sys.argv=[command]+argv
    runpy.run_module(COMMANDS[command],run_name='__main__')


if __name__ == '__main__':
    main()
