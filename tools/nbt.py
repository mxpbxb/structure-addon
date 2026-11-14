"""Minimal NBT reader/writer (Java edition, big endian). Tags are kept as (type, value) tuples
only where needed; compounds are dicts of name -> (type, value)."""
import gzip, io, struct

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY, LONG_ARRAY = range(13)


def _rs(f):
    n = struct.unpack('>H', f.read(2))[0]
    return f.read(n).decode('utf-8', 'replace')


def _read(f, t):
    if t == BYTE: return struct.unpack('>b', f.read(1))[0]
    if t == SHORT: return struct.unpack('>h', f.read(2))[0]
    if t == INT: return struct.unpack('>i', f.read(4))[0]
    if t == LONG: return struct.unpack('>q', f.read(8))[0]
    if t == FLOAT: return struct.unpack('>f', f.read(4))[0]
    if t == DOUBLE: return struct.unpack('>d', f.read(8))[0]
    if t == BYTE_ARRAY:
        n = struct.unpack('>i', f.read(4))[0]; return f.read(n)
    if t == STRING: return _rs(f)
    if t == LIST:
        et = f.read(1)[0]; n = struct.unpack('>i', f.read(4))[0]
        return (et, [_read(f, et) for _ in range(n)])
    if t == COMPOUND:
        d = {}
        while True:
            ct = f.read(1)[0]
            if ct == END: return d
            name = _rs(f)
            d[name] = (ct, _read(f, ct))
    if t == INT_ARRAY:
        n = struct.unpack('>i', f.read(4))[0]; return list(struct.unpack('>%di' % n, f.read(4 * n)))
    if t == LONG_ARRAY:
        n = struct.unpack('>i', f.read(4))[0]; return list(struct.unpack('>%dq' % n, f.read(8 * n)))
    raise ValueError('bad tag %d' % t)


def load_bytes(b):
    if b[:2] == b'\x1f\x8b':
        try:
            b = gzip.decompress(b)
        except Exception:
            import zlib
            b = zlib.decompressobj(31).decompress(b)
    f = io.BytesIO(b)
    t = f.read(1)[0]
    _rs(f)
    return _read(f, t)


def load(path):
    with open(path, 'rb') as fh:
        return load_bytes(fh.read())


def _ws(f, s):
    b = s.encode('utf-8'); f.write(struct.pack('>H', len(b))); f.write(b)


def _write(f, t, v):
    if t == BYTE: f.write(struct.pack('>b', v))
    elif t == SHORT: f.write(struct.pack('>h', v))
    elif t == INT: f.write(struct.pack('>i', v))
    elif t == LONG: f.write(struct.pack('>q', v))
    elif t == FLOAT: f.write(struct.pack('>f', v))
    elif t == DOUBLE: f.write(struct.pack('>d', v))
    elif t == BYTE_ARRAY: f.write(struct.pack('>i', len(v))); f.write(bytes(v))
    elif t == STRING: _ws(f, v)
    elif t == LIST:
        et, items = v
        if not items: et = END if et is None else et
        f.write(bytes([et])); f.write(struct.pack('>i', len(items)))
        for it in items: _write(f, et, it)
    elif t == COMPOUND:
        for k, (ct, cv) in v.items():
            f.write(bytes([ct])); _ws(f, k); _write(f, ct, cv)
        f.write(b'\x00')
    elif t == INT_ARRAY: f.write(struct.pack('>i', len(v))); f.write(struct.pack('>%di' % len(v), *v))
    elif t == LONG_ARRAY: f.write(struct.pack('>i', len(v))); f.write(struct.pack('>%dq' % len(v), *v))


def dump(path, root):
    f = io.BytesIO(); f.write(bytes([COMPOUND])); _ws(f, ''); _write(f, COMPOUND, root)
    with open(path, 'wb') as fh:
        fh.write(gzip.compress(f.getvalue()))


def plain(t, v):
    """Convert to plain python for inspection."""
    if t == COMPOUND: return {k: plain(*x) for k, x in v.items()}
    if t == LIST: return [plain(v[0], x) for x in v[1]]
    return v


# helpers to build tags
def S(v): return (STRING, v)
def I(v): return (INT, v)
def C(d): return (COMPOUND, d)
def L(t, items): return (LIST, (t, items))
