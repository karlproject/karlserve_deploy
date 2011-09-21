
def parse_dsn(dsn):
    args = {}
    for item in dsn.split():
        name, value = item.split('=')
        args[name] = value.strip("'")
    return args
