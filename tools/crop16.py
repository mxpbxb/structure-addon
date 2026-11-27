"""Crops a 32x32 stone texture to 16x16: the window (wrapping round the tile) whose own edges
join up best, so the crop still tiles without a visible seam. Reads and writes 8-bit RGB or RGBA,
non-interlaced PNGs (what Underground Biomes ships)."""
import struct, zlib


def read(path):
    data = open(path, 'rb').read()
    pos, idat = 8, b''
    while pos < len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8]); body = data[pos + 8:pos + 8 + n]
        if kind == b'IHDR':
            w, h, bd, ct, _, _, il = struct.unpack('>IIBBBBB', body)
            assert bd == 8 and ct in (2, 6) and il == 0, (path, bd, ct, il)
        elif kind == b'IDAT':
            idat += body
        pos += 12 + n
    bpp = 3 if ct == 2 else 4; stride = w * bpp
    raw = zlib.decompress(idat); rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]; line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0; b = prev[i]; c = prev[i - bpp] if i >= bpp else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line); prev = line
    return w, h, bpp, [[tuple(r[x * bpp:(x + 1) * bpp]) for x in range(w)] for r in rows]


def write(path, bpp, px):
    h, w = len(px), len(px[0])
    raw = b''.join(b'\0' + bytes(v for p in row for v in p) for row in px)
    def chunk(k, b): return struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k + b) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2 if bpp == 3 else 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def best_window(px, size=16):
    h, w = len(px), len(px[0])
    def d(p, q): return sum((a - b) ** 2 for a, b in zip(p[:3], q[:3]))
    best = None
    for oy in range(h):
        for ox in range(w):
            g = lambda x, y: px[(oy + y) % h][(ox + x) % w]
            # how unlike the crop's opposite edges are: the seam it would show when tiled
            seam = sum(d(g(0, y), g(size - 1, y)) for y in range(size)) + sum(d(g(x, 0), g(x, size - 1)) for x in range(size))
            if best is None or seam < best[0]:
                best = (seam, ox, oy)
    _, ox, oy = best
    return [[px[(oy + y) % h][(ox + x) % w] for x in range(size)] for y in range(size)]


def crop16(src, dst):
    w, h, bpp, px = read(src)
    write(dst, bpp, best_window(px) if w > 16 else px)
