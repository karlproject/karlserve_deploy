import datetime
import logging
import os
import shutil
import sys
import tempfile
import time

from karlserve.scripts.utils import shell
from karlserve.scripts.utils import shell_capture
from karlserve.scripts.utils import shell_pipe
from karlserve.scripts.utils import shell_script
from karlserve_deploy.utils import parse_dsn

log = logging.getLogger(__name__)

try:
    import pylibmc
else:
    pylibmc = None


def config_upgrade(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Upgrade production site.')
    parser.set_defaults(func=upgrade, parser=parser, instance=[],
                        only_one=True, subsystem='upgrade')


def config_migrate(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Migrate a site from an old installation.')
    parser.set_defaults(func=migrate, parser=parser, instance=[],
                        only_one=True, subsystem='upgrade')


@shell_script
def upgrade(args):
    # Calculate paths and do some sanity checking
    _get_paths(args)
    if args.this_build != args.current_build:
        args.parser.error("Upgrade must be run from current build.")
    if os.path.exists(args.next_build):
        args.parser.error("Next build directory already exists: %s" %
                          args.next_build)

    # Check out the next build and run the buildout
    git_url = args.get_setting('git_url')
    branch = args.get_setting('git_branch', 'master')
    shell('git clone --branch %s %s %s' % (branch, git_url, args.next_build))
    os.chdir(args.next_build)
    shell('virtualenv -p python2.6 --no-site-packages .')
    shell('bin/python bootstrap.py')
    shell('bin/buildout')

    # See whether this update requires an evolution step. If upgrade requires
    # an evolution step, we make backups of the instance databases before
    # running evolve.
    evolve_output = shell_capture('bin/karlserve evolve')
    needs_evolution = 'Not evolving' in evolve_output
    if needs_evolution:
        log.info("Evolution required.")

        # Put current build into readonly mode
        os.chdir(args.current_build)
        set_mode('readonly')

        # Dump databases for backup
        for name in args.instances:
            instance = args.get_instance(name)


            dbargs = parse_dsn(instance.config['dsn'])
            dumpfile = 'backup/%s-%s.dump' % (dbargs['dbname'],
                datetime.datetime.now().strftime('%Y.%m.%d.%H.%M.%S'))
            shell('ssh %s pg_dump -h localhost -U %s -f %s -F c %s' %
                  (dbargs['host'], dbargs['user'], dumpfile, dbargs['dbname']))

        # Run evolution step in next build
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


@shell_script
def migrate(args):
    # Calculate paths and do some sanity checking
    _get_paths(args)
    if args.this_build != args.current_build:
        args.parser.error("Upgrade must be run from current build.")

    for name in args.instances:
        migrate_instance(name, args)


def migrate_instance(name, args):
    instance = args.get_instance(name)
    config = instance.config

    # Is there any migration to do for this instance?
    do_migration = False
    for key in config:
        if key.startswith('migration'):
            do_migration = True
            break

    if not do_migration:
        return

    # Put instance in maintenance mode
    set_mode('maintenance', name)

    # Copy production data locally
    var = config['var']
    migration_data = os.path.join(var, 'migration', name)
    if not os.path.exists(migration_data):
        os.makedirs(migration_data)
    src = config['migration.db_file']
    dbfile = os.path.join(migration_data, 'karl.db')
    shell('rsync -z %s %s' % (src, dbfile))
    src = config['migration.blobs']
    blobdir = os.path.join(migration_data, 'blobs')
    if not os.path.exists(blobdir):
        os.mkdir(blobdir)
    shell('rsync -az --progress %s/ %s/' % (src, blobdir))

    # Clear memcached
    cache_servers = config.get('relstorage.cache_servers', None)
    if cache_servers is not None:
        print "Clearing memcached..."
        cache = pylibmc.Client(cache_servers.split(), binary=True)
        cache.flush_all()
        del cache

    # Delete current relstorage db
    dsn = parse_dsn(config['dsn'])
    ssh_host = 'postgres@%s' % dsn['host']
    shell('ssh %s dropdb %s' % (ssh_host, dsn['dbname']))
    shell('ssh %s createdb -O %s %s' % (ssh_host, dsn['user'], dsn['dbname']))

    # Convert ZEO data to relstorage
    tmp = tempfile.mkdtemp()
    try:
        zconfig = os.path.join(tmp, 'zodbconvert.conf')
        with open(zconfig, 'w') as out:
            out.write(zodbconvert_conf_template % {
                'blobdir': blobdir,
                'blob_cache': config['blob_cache'],
                'dbfile': dbfile,
                'dsn': config['dsn'],
            })
        shell('bin/zodbconvert %s' % zconfig)
        shell('rm -rf %s/*' % config['blob_cache'])
    finally:
        shutil.rmtree(tmp)

    if 'migration.dsn' in config:
        # Copy pgtextindex and repozitory
        src_dsn = parse_dsn(config['migration.dsn'])
        pg_dump = 'pg_dump -h localhost -U %s %s' % (
            src_dsn['user'], src_dsn['dbname'])
        pg_restore = 'psql -h localhost -U %s -q %s' % (
            dsn['user'], dsn['dbname'])
        if src_dsn['host'] != dsn['host']:
            script = 'ssh %s %s | %s' % (src_dsn['host'], pg_dump, pg_restore)
        else:
            script = "%s | %s" % (pg_dump, pg_restore)
        shell_pipe('ssh %s' % dsn['host'], script)
        reindex_text = False

    else:
        # Initialize pgtextindex and repozitory
        shell('bin/karlserve init_repozitory %s' % name)
        reindex_text = True

    karl_ini = config.get('migration.karl_ini')
    if karl_ini is not None:
        shell('bin/karlserve migrate_ini %s %s' % (name, karl_ini))

    shell('bin/karlserve evolve -I %s --latest' % name)
    set_mode('normal', name)

    if reindex_text:
        shell('bin/karlserve reindex_text --pg %s' % name)


def _get_paths(args):
    exe = os.path.realpath(sys.argv[0])
    args.this_build = os.path.dirname(os.path.dirname(exe))
    args.builds_dir = base = os.path.dirname(args.this_build)
    args.current_build = os.path.realpath(os.path.join(base, 'current'))
    current_index = os.path.split(args.current_build)[1]
    next_index = str(int(current_index) + 1)
    args.next_build = os.path.join(base, next_index)


def set_mode(mode, name=None):
    if name:
        shell('bin/karlserve mode -I %s -s %s' % (name, mode))
    else:
        shell('bin/karlserve mode -s %s' % mode)
    shell('bin/supervisorctl reload')


zodbconvert_conf_template = """\
<blobstorage source>
    blob-dir %(blobdir)s
    <filestorage>
        path %(dbfile)s
    </filestorage>
</blobstorage>

<relstorage destination>
    <postgresql>
        dsn %(dsn)s
    </postgresql>
    keep-history False
    shared-blob-dir False
    blob-dir %(blob_cache)s
    blob-cache-size 5gb
</relstorage>
"""
