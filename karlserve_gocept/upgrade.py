import logging
import os
import sys
import time

from karlserve.scripts.utils import shell
from karlserve.scripts.utils import shell_capture
from karlserve.scripts.utils import shell_script

from karlserve_gocept.utils import zeoinst


log = logging.getLogger(__name__)


def config_upgrade(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Upgrade production site.')
    parser.add_argument('--migrate', action='store_true',
                        help='Migrate data from old production.')
    parser.set_defaults(func=main, parser=parser, instance=[],
                        only_one=True, subsystem='upgrade')


@shell_script
def main(args):
    # Calculate paths and do some sanity checking
    _get_paths(args)
    if args.this_build != args.current_build:
        args.parser.error("Upgrade must be run from current build.")
    if os.path.exists(args.next_build):
        args.parser.error("Next build directory already exists: %s" %
                          args.next_build)

    if args.migrate:
        migrate(args)
    else:
        upgrade(args)


def upgrade(args):
    # Check out the next build and run the buildout
    git_url = args.get_setting('git_url')
    shell('git clone %s %s' % (git_url, args.next_build))
    os.chdir(args.next_build)
    shell('virtualenv -p python2.6 --no-site-packages .')
    shell('bin/python bootstrap.py')
    shell('bin/buildout')

    # See whether this update requires an evolution step. If upgrade requires
    # an evolution step, we make new copies of all instance databases before
    # running evolution.
    evolve_output = shell_capture('bin/karlserve evolve')
    needs_evolution = 'Not evolving' in evolve_output
    if needs_evolution:
        log.info("Evolution required.")

        # Make copy of database while current build is still running.  (Uses
        # rsync.)
        for name in args.instances:
            instance = args.get_instance(name)
            zeoinst('prep', instance.config)

        # Put the current build into maintenance mode
        os.chdir(args.current_build)
        _maint_mode()

        # Incrementally copy any new data in database since first copy was
        # initiated. (Uses rsync.)
        for name in args.instances:
            instance = args.get_instance(name)
            zeoinst('update', instance.config)

        # Run evolution step against new copy of database
        os.chdir(args.next_build)
        shell('bin/karlserve evolve --latest')

    else:
        log.info("Evolution not required.")

    # Update symlink pointer to make next build the current build
    link = os.path.join(os.path.dirname(args.next_build), 'current')
    os.remove(link)
    os.symlink(args.next_build, link)

    # Restart new build in normal mode
    shell('bin/karlserve mode -s normal')
    os.chdir(args.current_build)
    shell('bin/supervisorctl shutdown')
    log.info("Waiting for supervisor to shutown...")
    time.sleep(1)
    while os.path.exists('var/supervisord.pid'):
        log.info("Waiting...")
        time.sleep(1)
    os.chdir(args.next_build)
    shell('bin/supervisord')

def migrate(args):
    # Calculate paths and do some sanity checking
    _get_paths(args)
    if args.this_build != args.current_build:
        args.parser.error("Upgrade must be run from current build.")

    # Upgrade code in place (we're not really production, yet)
    os.chdir(args.current_build)
    shell('bin/buildout')

    for name in args.instances:
        migrate_instance(name, args)


def migrate_instance(name, args):
    _maint_mode(name)
    instance = args.get_instance(name)
    zeoinst('migrate', instance.config)
    karl_ini = instance.config.get('migration.karl_ini')
    shell('bin/karlserve migrate %s %s' % (name, karl_ini))
    shell('bin/karlserve evolve -I %s --latest' % name)
    _normal_mode(name)


def _get_paths(args):
    exe = os.path.realpath(sys.argv[0])
    args.this_build = os.path.dirname(os.path.dirname(exe))
    args.builds_dir = base = os.path.dirname(args.this_build)
    args.current_build = os.path.realpath(os.path.join(base, 'current'))
    current_index = os.path.split(args.current_build)[1]
    next_index = str(int(current_index) + 1)
    args.next_build = os.path.join(base, next_index)


def _maint_mode(name=None):
    if name:
        shell('bin/karlserve mode -I %s -s maintenance' % name)
    else:
        shell('bin/karlserve mode -s maintenance')
    shell('bin/supervisorctl reload')


def _normal_mode(name=None):
    if name:
        shell('bin/karlserve mode -I %s -s normal' % name)
    else:
        shell('bin/karlserve mode -s normal')
    shell('bin/supervisorctl reload')
