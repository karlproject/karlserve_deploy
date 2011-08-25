import os
import shutil
import sys

from karlserve.scripts.utils import shell
from karlserve.scripts.utils import shell_capture
from karlserve_gocept.utils import parse_dsn


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Clean up old buildout folders.')
    parser.add_argument('--keep', type=int, default=2,
                        help='Number of buildout folders to keep, not including the current.')
    parser.add_argument('--dumps', action='store_true', default=False,
                        help='Also clean up old data dumps on the db server.')
    parser.set_defaults(func=main, parser=parser, instance=[])


def main(args):
    if args.keep < 0:
        args.parser.error("Argument to --keep must be 0 or greater.")
    cleanup(args)
    if args.dumps:
        for name in args.instances:
            cleanup_dumps_instance(args, name)


def cleanup(args):
    print "Cleaning up old build directories."

    # Get current build dir
    exe = os.path.realpath(sys.argv[0])
    builddir = os.path.dirname(os.path.dirname(os.path.dirname(exe)))
    curdir = os.path.realpath(os.path.join(builddir, 'current'))
    if not os.path.exists(curdir):
        args.parser.error("No such folder: %s" % curdir)
    curdir = int(os.path.split(curdir)[1])

    # Get all build dirs
    subdirs = []
    for subdir in os.listdir(builddir):
        path = os.path.join(builddir, subdir)
        if os.path.isdir(path) and not os.path.islink(path):
            subdirs.append(int(subdir))
    subdirs.sort()

    # Compute folders to keep
    index = subdirs.index(curdir)
    keepers = [curdir]
    for i in range(args.keep):
        if index == 0:
            break
        index -= 1
        keepers.append(subdirs[index])

    # Compute folders to delete
    trash = [os.path.join(builddir, str(subdir)) for subdir in subdirs
             if subdir not in keepers]

    if not trash:
        print "Nothing to remove."
        return

    # Get user confirmation to delete
    print "The following folders will be deleted:"
    for path in trash:
        print "\t%s" % path
    print ""
    answer = ''
    while answer not in ('y', 'n', 'yes', 'no'):
        answer = raw_input("Delete these folders? (y or n) ").lower()
    if answer in ('y', 'yes'):
        for path in trash:
            print "Deleting", path
            shutil.rmtree(path)
        count = len(trash)
        if count == 1:
            print "One folder deleted."
        else:
            print "%d folders deleted." % count
    else:
        print "No folders deleted."


def cleanup_dumps_instance(args, name):
    print ""
    print "Clean up dumps for %s." % name
    instance = args.get_instance(name)
    config = instance.config
    dsn = parse_dsn(config['dsn'])
    host = dsn['host']

    ls = shell_capture('ssh %s ls backup' % host)
    fnames = [name for name in ls.split()
              if name.startswith(dsn['dbname']) and name.endswith('.dump')]

    if len(fnames) <= args.keep:
        print "Nothing to remove."
        return

    fnames.sort()
    trash = fnames[:-args.keep]

    print "The following dump files will be deleted:"
    for fname in trash:
        print "\t%s" % fname
    print ""
    answer = ''
    while answer not in ('y', 'n', 'yes', 'no'):
        answer = raw_input("Delete these folders? (y or n) ").lower()
    if answer in ('y', 'yes'):
        for fname in trash:
            shell("ssh %s rm backup/%s" % (host, fname))
        count = len(trash)
        if count == 1:
            print "One file deleted."
        else:
            print "%d files deleted." % count
    else:
        print "No files deleted."
