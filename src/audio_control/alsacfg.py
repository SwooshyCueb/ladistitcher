import io, collections
from contextlib import contextmanager

indent_lvl = 0
compounds = [dict, collections.OrderedDict, collections.defaultdict]
arrays = [list, tuple, range, set, frozenset, collections.deque]

def gen_alsa_cfg(cfg):
    global indent_lvl
    indent_lvl = 0
    cfg_io = io.StringIO()

    @contextmanager
    def indent_inc():
        global indent_lvl
        indent_lvl += 1
        yield
        indent_lvl -= 1

    def write_indent():
        cfg_io.write('  ' * indent_lvl)

    def write_compound(value):
        cfg_io.write('{\n')
        with indent_inc():
            for key, item in value.items():
                write_variable(key, item)
        write_indent()
        cfg_io.write('}\n')

    def write_array(value):
        cfg_io.write('[\n')
        with indent_inc():
            for item in value:
                write_variable(item)
        write_indent()
        cfg_io.write(']\n')

    def write_variable(var, val=None):
        global indent_lvl
        write_indent

        if val != None:
            cfg_io.write(str(var) + ' ')
            value = val
        else:
            value = var
        if type(value) in compounds:
            write_compound(value)
        elif type(value) in arrays:
            write_array(value)
        else:
            cfg_io.write(str(val) + '\n')

    for key, value in cfg.items():
        cfg_io.write(str(key) + ' ')

    cfg = cfg_io.getvalue
    cfg_io.close()

    return cfg
