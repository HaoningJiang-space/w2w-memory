"""Usage: python -m w2w COMMAND [arguments]."""
import argparse
import runpy
import sys
from w2w.commands import COMMANDS, COMMAND_SCOPES, COMMAND_STATUS


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help', '--list'):
        parser = argparse.ArgumentParser(prog='python -m w2w', add_help=False)
        parser.add_argument('-h', '--help', action='store_true')
        parser.add_argument('--list', action='store_true')
        parser.add_argument('--scope', choices=('current', 'reference', 'legacy'))
        options = parser.parse_args(argv)
        groups = (options.scope,) if options.scope else (
            ('current', 'reference', 'legacy') if options.list else ('current',))
        print('Usage: python -m w2w COMMAND [arguments]\n')
        print('Commands (original names remain available):')
        for group in groups:
            print('\n  '+group.capitalize()+':')
            for name,module in COMMANDS.items():
                if COMMAND_STATUS[name] == group:
                    print('    '+name+' ['+COMMAND_SCOPES[name]+']')
        print('\nAll entries: --list; filter: --list --scope current|reference|legacy')
        print('Builds, tests and experiments: isolated hn072 workspace; see docs/HANDOFF.md')
        return
    command = argv.pop(0).removesuffix('.py')
    if command not in COMMANDS:
        parser=argparse.ArgumentParser(prog='python -m w2w')
        parser.error('unknown command '+repr(command)+'; use --list')
    sys.argv=[command]+argv
    # Multiprocessing must find dispatched top-level workers in sys.modules.
    runpy.run_module(COMMANDS[command],run_name='__main__',alter_sys=True)


if __name__ == '__main__':
    main()
