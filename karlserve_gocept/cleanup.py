import os
import shutil
import sys


def zeoinst(*args, **kw):
    raise NotImplementedError()


def config_parser(name, subparsers, **helpers):
    parser = subparsers.add_parser(
        name, help='Clean up old buildout folders.')
    parser.add_argument('--keep', type=int, default=2,
                        help='Number of buildout folders to keep, not including the current.')
    parser.add_argument('--zeo', action='store_true', default=False,
                        help='Also clean up old data folders in zeo instances.')
    parser.set_defaults(func=main, parser=parser, instance=[])


def main(args):
    cleanup(args)
    if args.zeo:
        for name in args.instances:
            instance = args.get_instance(name)
            zeoinst('cleanup', instance.config, '--keep %d' % args.keep)


def cleanup(args):
    if args.keep < 0:
        args.parser.error("Argument to --keep must be 0 or greater.")

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
