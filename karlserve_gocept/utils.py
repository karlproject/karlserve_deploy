from karlserve.scripts.utils import shell


def zeoinst(command, config, args=''):
    remote_zeo = config.get('zeo_host')
    if remote_zeo:
        remote_user = config.get('zeo_user')
        if remote_user:
            remote_zeo = '%s@%s' % (remote_user, remote_zeo)

    zeoinst = config.get('zeoinst')
    assert zeoinst, "'zeoinst' is not configured."
    if remote_zeo:
        shell('ssh -t %s %s %s %s' % (remote_zeo, zeoinst, command, args))
    else:
        shell('%s %s %s' % (zeoinst, command, args))
