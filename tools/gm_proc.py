# Generatormods' generated structures, rebuilt as data (exec'd by gen.py, sharing its globals):
#  - Cellular-automaton ruins: Formivore's automaton (seed grown layer by layer by a birth/survive
#    rule, flipped, partly buried, with floors, ladders, chests and spawners), pre-grown variants.
#  - Great Walls: jigsaw chains of wall pieces (each TML's cross-section) that follow the terrain,
#    with square or round towers, turning at towers, ending in an end tower.
#  - Walled cities: a plaza, four streets to four gates, a closed wall ring with corner towers, and
#    buildings along the streets and side streets: the street's TML buildings and generated houses.
#  - Underground cities: the same street plan carved into the rock, lit by lanterns.
GMP = 'generatormods'
AIR = ('minecraft:air', {})
FACES = ('north', 'east', 'south', 'west')
FACE_V = {'north': (0, -1), 'south': (0, 1), 'east': (1, 0), 'west': (-1, 0)}
OPP = {'north': 'south', 'south': 'north', 'east': 'west', 'west': 'east'}
BUILDING = GMP + ':building'
GMB = {'Forest': TOK['FOREST'], 'ForestHills': TOK['FOREST'], 'Swampland': TOK['SWAMP'],
       'Mushroom Island': TOK['MUSHROOM'], 'Taiga': TOK['CONIFEROUS'], 'Plains': TOK['PLAINS'],
       'Desert': TOK['DESERT'], 'DesertHills': TOK['DESERT'], 'Jungle': TOK['JUNGLE'],
       'ExtremeHills': TOK['MOUNTAIN'], 'Ocean': set(), 'River': set(), 'Sky': set(), 'Hell': set(),
       'Underground': set()}
GM_REPORT = REPORT.setdefault('gm_generated', collections.OrderedDict())


def fstate(st):
    n, p = st[0], st[1]
    return n + ('[' + ','.join('%s=%s' % kv for kv in sorted(p.items())) + ']' if p else '')


class Piece:
    def __init__(self):
        self.g, self.be, self.ents = {}, {}, []

    def set(self, pos, st, be=None):
        if st is None:
            return
        self.g[pos] = [st[0], dict(st[1])]
        if be:
            self.be[pos] = be
        else:
            self.be.pop(pos, None)

    def air(self, pos):
        self.set(pos, AIR)

    def jig(self, pos, facing, name, target, pool, prio=0):
        cur = self.g.get(pos)
        fin = fstate(cur) if cur and cur[0] != 'minecraft:jigsaw' else 'minecraft:air'
        self.g[pos] = ['minecraft:jigsaw', {'orientation': facing + '_up'}]
        self.be[pos] = {'id': nbt.S('minecraft:jigsaw'), 'name': nbt.S(name), 'target': nbt.S(target),
                        'pool': nbt.S(pool), 'final_state': nbt.S(fin), 'joint': nbt.S('aligned'),
                        'placement_priority': nbt.I(prio), 'selection_priority': nbt.I(prio)}

    def write(self, loc):
        if not self.g:
            self.g[(0, 0, 0)] = list(AIR)
        mn = [min(p[i] for p in self.g) for i in range(3)]
        mx = [max(p[i] for p in self.g) for i in range(3)]
        sh = lambda p: (p[0] - mn[0], p[1] - mn[1], p[2] - mn[2])
        grid = {sh(p): v for p, v in self.g.items()}
        bents = {sh(p): v for p, v in self.be.items()}
        ents = [(x - mn[0], y - mn[1], z - mn[2], e) for x, y, z, e in self.ents]
        write_template('data/%s/structure/%s.nbt' % (GMP, loc), tuple(mx[i] - mn[i] + 1 for i in range(3)), grid, bents, ents)
        return GMP + ':' + loc


def pool(name, elements, fallback='minecraft:empty'):
    els = []
    for loc, w, proj in elements:
        if loc is None:
            els.append({'element': {'element_type': 'minecraft:empty_pool_element'}, 'weight': w})
        else:
            els.append({'element': {'element_type': 'minecraft:single_pool_element', 'location': loc,
                                    'processors': 'minecraft:empty', 'projection': proj}, 'weight': w})
    wjson('data/%s/worldgen/template_pool/%s.json' % (GMP, name), {'elements': els, 'fallback': fallback})
    return GMP + ':' + name


def biome_tag(name, biomes):
    wjson('data/%s/tags/worldgen/biome/has_structure/%s.json' % (GMP, name), {'values': biomes})
    return '#%s:has_structure/%s' % (GMP, name)


def gm_biomes(head, default=None):
    names = [b.strip() for b in head.get('biomes', '').split(',') if b.strip()]
    s = set()
    for b in names:
        s |= GMB.get(b, set())
    s &= BIOMES
    if s:
        return ['minecraft:' + b for b in sorted(s)]
    return default or ['#minecraft:is_overworld']


# ---------------------------------------------------------------- block choices
def rule_literal(text):
    f = [t.strip() for t in text.split('#')[0].split(',')]
    if len(f) >= 3 and f[1].isdigit():
        return (int(f[1]), [t for t in f[2:] if t])
    return None


def picker(rule, rng, solid=False, fallback=('minecraft:cobblestone', {})):
    """A function giving one block (state, be) of `rule` each call; None for a skipped one."""
    def pick():
        for _ in range(6 if solid else 1):
            if not rule or not rule[1]:
                break
            if rng.randint(1, 100) > rule[0]:
                if solid:
                    continue
                return None
            r = tml_token(rng.choice(rule[1]), rng)
            if r[0] == 'block' and r[1][0] != 'minecraft:air':
                return (r[1], r[2])
            if not solid:
                return (AIR, None) if r[0] == 'block' else None
        return (fallback, None) if solid else None
    return pick


def base_of(rule, rng):
    for t in (rule[1] if rule else []):
        r = tml_token(t, rng)
        if r[0] == 'block' and r[1][0] != 'minecraft:air':
            return r[1]
    return ('minecraft:cobblestone', {})


STAIR_BASE = {'cobblestone': 'cobblestone', 'mossy_cobblestone': 'mossy_cobblestone', 'stone_bricks': 'stone_brick',
              'mossy_stone_bricks': 'mossy_stone_brick', 'cracked_stone_bricks': 'stone_brick',
              'chiseled_stone_bricks': 'stone_brick', 'sandstone': 'sandstone', 'chiseled_sandstone': 'sandstone',
              'cut_sandstone': 'sandstone', 'smooth_sandstone': 'smooth_sandstone', 'red_sandstone': 'red_sandstone',
              'bricks': 'brick', 'nether_bricks': 'nether_brick', 'stone': 'stone', 'oak_planks': 'oak',
              'spruce_planks': 'spruce', 'birch_planks': 'birch', 'jungle_planks': 'jungle', 'acacia_planks': 'acacia',
              'dark_oak_planks': 'dark_oak', 'oak_log': 'oak', 'spruce_log': 'spruce', 'birch_log': 'birch',
              'quartz_block': 'quartz', 'obsidian': 'polished_blackstone', 'end_stone': 'end_stone_brick',
              'prismarine': 'prismarine', 'granite': 'granite', 'andesite': 'andesite', 'diorite': 'diorite',
              'smooth_stone': 'stone', 'snow_block': 'stone_brick', 'ice': 'stone_brick', 'packed_ice': 'stone_brick'}


def stair_kind(block_name):
    return STAIR_BASE.get(block_name.split(':')[1], 'cobblestone')


def stairs(kind, facing, half='bottom'):
    return ('minecraft:%s_stairs' % kind, {'facing': facing, 'half': half, 'shape': 'straight', 'waterlogged': 'false'})


def slab(kind, typ='bottom'):
    n = 'minecraft:%s_slab' % kind
    if kind == 'stone_brick':
        n = 'minecraft:stone_brick_slab'
    return (n, {'type': typ, 'waterlogged': 'false'})


def roof_kind_for(block_name):
    k = stair_kind(block_name)
    return k if k in ('sandstone', 'smooth_sandstone', 'red_sandstone', 'nether_brick', 'quartz') else 'spruce'


# ---------------------------------------------------------------- towers and houses
def footprint(S, circular):
    cells = set()
    if circular:
        c = (S - 1) / 2.0
        r2 = (S / 2.0) ** 2 - 0.3
        for x in range(S):
            for z in range(S):
                if (x - c) ** 2 + (z - c) ** 2 <= r2:
                    cells.add((x, z))
    else:
        cells = {(x, z) for x in range(S) for z in range(S)}
    wall = {p for p in cells if any((p[0] + dx, p[1] + dz) not in cells for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))}
    return cells, wall


def side_cell(cells, S, face):
    c = S // 2
    if face == 'north':
        return (c, min(z for x, z in cells if x == c))
    if face == 'south':
        return (c, max(z for x, z in cells if x == c))
    if face == 'west':
        return (min(x for x, z in cells if z == c), c)
    return (max(x for x, z in cells if z == c), c)


def put_roof(P, cells, S, top, style, mat, kind, rng, circular):
    """Roof over the footprint, its lowest course at y=top."""
    xs = [x for x, z in cells]
    if style == 'Crenel' or (circular and style not in ('Dome', 'Steep')):
        for (x, z) in cells:
            if (x, z) in footprint(S, circular)[1] and (x + z) % 2 == 0:
                P.set((x, top, z), *mat())
        return
    if style == 'Dome':
        c = (S - 1) / 2.0
        r = S / 2.0
        for (x, z) in cells:
            d2 = (x - c) ** 2 + (z - c) ** 2
            for y in range(int(r) + 1):
                if d2 + (y + 0.5) ** 2 <= r * r and d2 + (y + 1.5) ** 2 > r * r - 2 * r:
                    P.set((x, top + y, z), *mat())
        return
    if style == 'Two Sided':
        k = 0
        while True:
            lo, hi = k, S - 1 - k
            if lo > hi:
                break
            for z in range(S):
                if lo == hi:
                    P.set((lo, top + k, z), slab(kind))
                else:
                    P.set((lo, top + k, z), stairs(kind, 'east'))
                    P.set((hi, top + k, z), stairs(kind, 'west'))
            for x in range(lo + 1, hi):
                for z in (0, S - 1):
                    P.set((x, top + k, z), *mat())
            k += 1
        return
    # Steep, Steep Trim and Shallow: a pyramid of stairs (Shallow: slabs, half the rise)
    shallow = style == 'Shallow'
    k = 0
    while True:
        lo, hi = k, S - 1 - k
        if lo > hi:
            break
        y = top + (k // 2 if shallow else k)
        for x in range(lo, hi + 1):
            for z in range(lo, hi + 1):
                if lo < x < hi and lo < z < hi:
                    continue
                if shallow:
                    P.set((x, y, z), slab(kind, 'bottom' if k % 2 == 0 else 'top'))
                elif lo == hi:
                    P.set((x, y, z), slab(kind))
                else:
                    f = 'south' if z == lo else 'north' if z == hi else 'east' if x == lo else 'west'
                    P.set((x, y, z), stairs(kind, f))
        k += 1


def build_tower(P, S, H, mat, roof, kind, rng, circular=False, doors=(), floors_every=5, spawner=None,
                chest=None, furniture=False, windows=True, house_door=None):
    cells, wall = footprint(S, circular)
    inner = cells - wall
    for y in range(H):
        floor = y == 0 or (y % floors_every == 0 and y < H - 1) or y == H - 1
        for (x, z) in cells:
            if (x, z) in wall or floor:
                P.set((x, y, z), *mat())
            else:
                P.air((x, y, z))
    # ladder up the inside of the north wall
    lad = sorted((p for p in inner if (p[0], p[1] - 1) in wall), key=lambda p: abs(p[0] - S // 2))
    if lad and H > 4:
        lx, lz = lad[0]
        for y in range(1, H):
            P.set((lx, y, lz), ('minecraft:ladder', {'facing': 'south', 'waterlogged': 'false'}))
    # doors and windows
    for face, y0 in doors:
        x, z = side_cell(cells, S, face)
        for y in (y0, y0 + 1):
            if 0 < y < H:
                P.air((x, y, z))
    if house_door:
        x, z = side_cell(cells, S, house_door)
        f = house_door
        P.set((x, 1, z), ('minecraft:oak_door', {'facing': OPP[f], 'half': 'lower', 'hinge': 'left', 'open': 'false', 'powered': 'false'}))
        P.set((x, 2, z), ('minecraft:oak_door', {'facing': OPP[f], 'half': 'upper', 'hinge': 'left', 'open': 'false', 'powered': 'false'}))
    if windows:
        for base in range(0, H - 2, floors_every):
            for face in FACES:
                if house_door == face and base == 0:
                    continue
                x, z = side_cell(cells, S, face)
                y = base + 2
                if 0 < y < H - 1 and P.g.get((x, y, z), [''])[0] != 'minecraft:oak_door':
                    if furniture:
                        P.set((x, y, z), ('minecraft:glass_pane', {'north': 'false', 'south': 'false', 'east': 'false', 'west': 'false', 'waterlogged': 'false'}))
                    else:
                        P.air((x, y, z))
    put_roof(P, cells, S, H, roof, mat, kind, rng, circular)
    floors = [y for y in range(0, H - 1, floors_every)]
    free = lambda y: [p for p in sorted(inner) if P.g.get((p[0], y + 1, p[1]), [''])[0] == 'minecraft:air'
                      and P.g.get((p[0], y + 2, p[1]), [''])[0] == 'minecraft:air']
    if spawner:
        y = floors[-1]
        f = free(y)
        if f:
            x, z = rng.choice(f)
            r = spawner
            if r[0] == 'entity':
                P.ents.append((x, y + 1, z, r[1]))
            elif r[0] == 'block':
                P.set((x, y + 1, z), r[1], r[2])
    if chest:
        y = rng.choice(floors)
        f = free(y)
        if f:
            x, z = rng.choice(f)
            P.set((x, y + 1, z), ('minecraft:chest', {'facing': 'south', 'type': 'single', 'waterlogged': 'false'}),
                  {'id': nbt.S('minecraft:chest'), 'LootTable': nbt.S(chest)})
    if furniture:
        f = [p for p in free(0) if any((p[0] + dx, p[1] + dz) in wall for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        rng.shuffle(f)
        for blk in (('minecraft:crafting_table', {}), ('minecraft:furnace', {'facing': 'south', 'lit': 'false'}),
                    ('minecraft:bookshelf', {}), ('minecraft:torch', {})):
            if f:
                x, z = f.pop()
                P.set((x, 1, z), blk)
    return cells


def spawner_token(text, rng):
    lit = rule_literal(text) if text else None
    if not lit or rng.randint(1, 100) > lit[0]:
        return None
    r = tml_token(rng.choice(lit[1]), rng)
    return r if r[0] in ('entity', 'block') else None


def tower_spec(head):
    g = lambda k, d: int(head.get(k, d) or d)
    return dict(sq=(g('square_min_width', 7), max(g('square_min_width', 7), g('square_max_width', 7)),
                    g('square_min_height', 10), max(g('square_min_height', 10), g('square_max_height', 14))),
                ci=(g('circular_tower_min_width', 8), max(g('circular_tower_min_width', 8), g('circular_tower_max_width', 10)),
                    g('circular_tower_min_height', 10), max(g('circular_tower_min_height', 10), g('circular_tower_max_height', 14))),
                circ=float(head.get('circular_probability', '0') or 0),
                sq_roofs=[r.strip() for r in head.get('square_roof_styles', 'Crenel').split(',') if r.strip()] or ['Crenel'],
                ci_roofs=[r.strip() for r in head.get('circular_tower_roof_styles', 'Crenel').split(',') if r.strip()] or ['Crenel'],
                spawner=head.get('spawner_rule', ''), mob_p=float(head.get('mob_probability', '1') or 1),
                furniture=head.get('populate_furniture', '0') == '1', doors=head.get('make_doors', '0') == '1',
                tower_rule=head.get('tower_rule', '1'))


def tower_rule_of(spec, rules):
    tr = spec['tower_rule']
    if ',' in tr:
        return rule_literal(tr)
    try:
        return rules.get(int(tr.split('#')[0].strip()))
    except ValueError:
        return rules.get(1)


# ---------------------------------------------------------------- cellular-automaton ruins
CA_RULES = [('B3', 'S23', 5), ('B36', 'S013468', 3), ('B367', 'S02347', 2), ('B34', 'S2356', 3), ('B368', 'S245', 8),
            ('B36', 'S125', 4), ('B36', 'S23', 4), ('B3568', 'S148', 4), ('B3', 'S1245', 8), ('B3567', 'S13468', 5),
            ('B356', 'S16', 5), ('B3468', 'S123', 3), ('B35678', 'S015678', 2), ('B35678', 'S0156', 15),
            ('B26', 'S12368', 1), ('B248', 'S45', 1), ('B2457', 'S013458', 1), ('B45', 'S2345', 6)]
CA_MATERIALS = {  # name -> (block rule tokens, biomes)
    'mossy': (['4-0', '48-0', '48-0'], ['#minecraft:is_forest', '#minecraft:is_taiga', '#minecraft:is_jungle',
                                         'minecraft:swamp', 'minecraft:mangrove_swamp', '#minecraft:is_savanna',
                                         '#minecraft:is_badlands', 'minecraft:mushroom_fields', '#minecraft:is_beach']),
    'stone': (['1-0', '98-1', '98-2'], ['minecraft:plains', 'minecraft:sunflower_plains', 'minecraft:meadow',
                                         '#minecraft:is_hill', 'minecraft:stony_shore', 'minecraft:stony_peaks']),
    'sandstone': (['24-0'], ['minecraft:desert']),
    'snow': (['80-0', '98-2', '98-2'], ['minecraft:snowy_plains', 'minecraft:ice_spikes', 'minecraft:snowy_taiga',
                                        'minecraft:snowy_slopes', 'minecraft:grove', 'minecraft:frozen_peaks']),
}
CA_SPAWN_LOW = ['zombie', 'skeleton', 'silverfish', 'magma_cube', 'cave_spider']
CA_SPAWN_WIDE = ['blaze', 'silverfish', 'silverfish', 'cave_spider', 'cave_spider', 'spider']
CA_SPAWN_NARROW = ['blaze', 'blaze', 'blaze', 'silverfish', 'silverfish', 'magma_cube']


def circle_val(d, x, y):
    c = (d - 1) / 2.0
    dist = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
    return 1 if dist <= d / 2.0 - 0.5 else 0 if dist <= d / 2.0 else -1


def ca_seed(rng, kind, maxw, density=0.5):
    if kind == 1:  # linear
        w = rng.randrange(rng.randrange(maxw - 1) + 1) + 2
        return [[1] for _ in range(w)]
    if kind == 2:  # circular
        d = min(rng.randrange(rng.randrange(rng.randrange(max(1, maxw - 4)) + 1) + 1) + 4, 40)
        return [[1 if circle_val(d, x, y) == 1 else 0 for y in range(d)] for x in range(d)]
    if kind == 3:  # cruciform
        w = 2 * (rng.randrange(rng.randrange(maxw // 2) + 1) + 1) + 1
        l = 2 * (rng.randrange(rng.randrange(maxw // 2) + 1) + 1) + 1
        return [[1 if (x == w // 2 or y == l // 2) else 0 for y in range(l)] for x in range(w)]
    mw = rng.randrange(rng.randrange(max(1, maxw - 4)) + 1) + 1
    w = rng.randrange(rng.randrange(mw) + 1) + 4
    l = rng.randrange(rng.randrange(mw) + 1) + 4
    seed = [[0] * l for _ in range(w)]
    d = min(max(w, l), 40)
    for x in range((w + 1) // 2):
        for y in range((l + 1) // 2):
            v = 1 if circle_val(d, x, y) >= 0 and rng.random() < density else 0
            seed[x][y] = seed[w - x - 1][y] = seed[x][l - y - 1] = seed[w - x - 1][l - y - 1] = v
    return seed


def ca_plan(rule, seed, W, H, L, min_osc=12):
    birth = [1 if str(i) in rule[0][1:] else 0 for i in range(9)]
    surv = [1 if str(i) in rule[1][1:] else 0 for i in range(9)]
    if (W - len(seed)) % 2:
        W += 1
    if (L - len(seed[0])) % 2:
        L += 1
    layers = [[[0] * L for _ in range(W)] for _ in range(H)]
    BB = [[0] * H for _ in range(4)]
    BB[0][0] = (W - len(seed)) // 2; BB[1][0] = BB[0][0] + len(seed) - 1
    BB[2][0] = (L - len(seed[0])) // 2; BB[3][0] = BB[2][0] + len(seed[0]) - 1
    for x in range(len(seed)):
        for y in range(len(seed[0])):
            layers[0][BB[0][0] + x][BB[2][0] + y] = seed[x][y]
    cryst = -1
    for z in range(1, H):
        alive = False
        fixed = cryst == -1
        p2 = cryst == -1 and z >= 2
        p3 = cryst == -1 and z >= 3
        BB[0][z] = BB[1][z] = W // 2
        BB[2][z] = BB[3][z] = L // 2
        for x in range(max(0, BB[0][z - 1] - 1), min(W - 1, BB[1][z - 1] + 1) + 1):
            for y in range(max(0, BB[2][z - 1] - 1), min(L - 1, BB[3][z - 1] + 1) + 1):
                n = 0
                for x1 in range(max(x - 1, 0), min(x + 1, W - 1) + 1):
                    for y1 in range(max(y - 1, 0), min(y + 1, L - 1) + 1):
                        if not (x1 == x and y1 == y):
                            n += layers[z - 1][x1][y1]
                v = (birth if layers[z - 1][x][y] == 0 else surv)[n]
                layers[z][x][y] = v
                if v:
                    BB[0][z] = min(BB[0][z], x); BB[1][z] = max(BB[1][z], x)
                    BB[2][z] = min(BB[2][z], y); BB[3][z] = max(BB[3][z], y)
                    alive = True
                if v != layers[z - 1][x][y]:
                    fixed = False
                if z >= 2 and v != layers[z - 2][x][y]:
                    p2 = False
                if z >= 3 and v != layers[z - 3][x][y]:
                    p3 = False
        if not alive:
            if z <= min_osc:
                return None
            H = z
            break
        if fixed:
            if z - 1 <= min_osc:
                return None
            cryst = z - 1
        if p2:
            if z - 2 <= min_osc:
                return None
            cryst = z - 2
        if p3:
            if z - 3 <= min_osc:
                return None
            cryst = z - 3
        if cryst > -1 and z > 2 * cryst:
            H = z
            break
    top = sum(map(sum, layers[0])); second = sum(map(sum, layers[1]))
    if 2 * top >= 3 * second:
        for x in range(W):
            for y in range(L):
                if layers[0][x][y] and not layers[1][x][y]:
                    layers[0][x][y] = 0
    minX, maxX = min(BB[0][:H]), max(BB[1][:H])
    minY, maxY = min(BB[2][:H]), max(BB[3][:H])
    w, l = maxX - minX + 1, maxY - minY + 1
    out = []
    fBB = [[0] * H for _ in range(4)]
    for z in range(H):
        lz = H - z - 1
        out.append([[layers[lz][x + minX][y + minY] for y in range(l)] for x in range(w)])
        fBB[0][z] = BB[0][lz] - minX + (BB[1][lz] - BB[0][lz]) // 4
        fBB[1][z] = BB[1][lz] - minX - (BB[1][lz] - BB[0][lz]) // 4
        fBB[2][z] = BB[2][lz] - minY + (BB[3][lz] - BB[2][lz]) // 4
        fBB[3][z] = BB[3][lz] - minY - (BB[3][lz] - BB[2][lz]) // 4
    return out, fBB, w, H, l


def ca_build(rng, layers, fBB, w, H, l, mat_tokens, two_rule):
    rule = (100, mat_tokens)
    mat = picker(rule, rng, solid=True)
    kind = stair_kind(base_of(rule, rng)[0])
    P = Piece()
    A = lambda x, z, y: 0 <= z < H and 0 <= x < w and 0 <= y < l and layers[z][x][y] == 1
    zg = max(0, H - w // 3 - rng.randrange(max(1, w))) if two_rule else rng.randrange(max(1, 3 * H // 4))
    cx = (fBB[0][0] + fBB[1][0]) // 2
    hole = [[cx, cx + 1] for _ in range(l)]
    floor_pts = {z: [] for z in range(H)}
    for z in range(H - 1, -1, -1):
        for x in range(w):
            for y in range(l):
                if A(x, z, y):
                    P.set((x, z, y), *mat())
                elif z > 0 and A(x, z - 1, y):
                    if z < H - 5 and fBB[0][z] <= x <= fBB[1][z] and fBB[2][z] <= y <= fBB[3][z]:
                        floor_pts[z].append((x, y))
                        hole[y][0] = min(hole[y][0], max(fBB[0][z], x - 2))
                        hole[y][1] = max(hole[y][1], min(fBB[1][z], x + 2))
                    elif z == H - 1 or not A(x, z + 1, y):
                        if A(x, z, y + 1) and not A(x, z, y - 1):
                            P.set((x, z, y), stairs(kind, 'south'))
                        elif A(x, z, y - 1) and not A(x, z, y + 1):
                            P.set((x, z, y), stairs(kind, 'north'))
                        elif A(x + 1, z, y) and not A(x - 1, z, y):
                            P.set((x, z, y), stairs(kind, 'east'))
                        elif A(x - 1, z, y) and not A(x + 1, z, y):
                            P.set((x, z, y), stairs(kind, 'west'))
        for y in range(l):
            for x in range(hole[y][0] + 1, hole[y][1]):
                if not A(x, z, y) and (x, z, y) not in P.g:
                    P.air((x, z, y))
        if z % 2 == 0:
            for y in range(l):
                hole[y][0] = hole[y][0] + 1 if hole[y][0] < cx else cx
                hole[y][1] = hole[y][1] - 1 if hole[y][1] > cx + 1 else cx + 1
    solid = lambda x, z, y: P.g.get((x, z, y), ['minecraft:air'])[0] != 'minecraft:air'
    counts = {z: len(floor_pts[z]) for z in range(H)}
    floors = []
    while True:
        best, bz = counts.get(1, 0), 1
        for f in range(2, H - 5):
            s = counts.get(f - 1, 0) + counts.get(f, 0) + counts.get(f + 1, 0)
            if s > best:
                best, bz = s, f
        if best <= 20:
            break
        done = set()
        for zz in (bz - 1, bz, bz + 1):
            for (x, y) in floor_pts.get(zz, []):
                for (px, py) in ((x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if (px, py) in done or not (0 <= px < w and 0 <= py < l):
                        continue
                    done.add((px, py))
                    if solid(px, bz, py) and solid(px, bz + 1, py):
                        continue
                    if not solid(px, bz - 1, py):
                        P.set((px, bz - 1, py), *mat())
                    P.air((px, bz, py)); P.air((px, bz + 1, py))
        floors.append((bz, best, sorted(done)))
        for d in range(-3, 4):
            counts[bz + d] = 0
    floors.sort()
    for i, (fz, cnt, pts) in enumerate(floors):
        walk = [p for p in pts if solid(p[0], fz - 1, p[1]) and not solid(p[0], fz, p[1]) and not solid(p[0], fz + 1, p[1])]
        if not walk:
            continue
        if rng.random() < 0.7:
            x, y = rng.choice(walk)
            mobs = CA_SPAWN_LOW if fz < zg else (CA_SPAWN_WIDE if cnt > 70 else CA_SPAWN_NARROW)
            P.set((x, fz, y), ('minecraft:spawner', {}), {'id': nbt.S('minecraft:mob_spawner'), 'SpawnData': nbt.C(
                {'entity': nbt.C({'id': nbt.S('minecraft:' + rng.choice(mobs))})})})
        if rng.random() < 0.5:
            x, y = rng.choice(walk)
            deep = abs(zg - fz) > 10
            loot = rng.choice(['minecraft:chests/abandoned_mineshaft', 'minecraft:chests/stronghold_corridor'] if deep
                              else ['minecraft:chests/simple_dungeon', 'minecraft:chests/abandoned_mineshaft'])
            P.set((x, fz - 1, y), ('minecraft:chest', {'facing': 'north', 'type': 'single', 'waterlogged': 'false'}),
                  {'id': nbt.S('minecraft:chest'), 'LootTable': nbt.S(loot)})
        if i > 0:  # ladder from the floor below
            lz = floors[i - 1][0]
            for (x, y) in walk:
                if solid(x + 1, fz, y) or True:
                    for zz in range(lz, fz):
                        if not solid(x, zz, y) or P.g.get((x, zz, y), [''])[0] == 'minecraft:air':
                            P.set((x, zz, y), ('minecraft:ladder', {'facing': 'west', 'waterlogged': 'false'}))
                        P.set((x + 1, zz, y), *mat())
                    break
    return P, zg


ca_list = []
crng = random.Random('generatormods-ca')
for mname, (toks, biomes) in CA_MATERIALS.items():
    made = 0
    tries = 0
    while made < 7 and tries < 400:
        tries += 1
        r = crng.choices(CA_RULES, weights=[c[2] for c in CA_RULES])[0]
        four = not any(str(i) in r[0][1:] for i in range(4))
        sk = crng.choices([0, 1, 2, 3], weights=[8, 2, 2, 1])[0]
        seed = ca_seed(crng, 0 if four else sk, 40)
        th = 20 + crng.randrange(51)
        res = ca_plan(r, seed, 40, th, 40)
        if not res:
            continue
        layers, fBB, w, H, l = res
        if w * l < 9:
            continue
        P, zg = ca_build(crng, layers, fBB, w, H, l, toks, '2' in r[0][1:])
        name = 'ca_ruin_%s_%d' % (mname, made)
        P.write('ca/' + name)
        ca_list.append((name, mname, zg, r[0] + '/' + r[1]))
        made += 1
for name, mname, zg, rl in ca_list:
    tag = biome_tag(name, CA_MATERIALS[mname][1])
    p = pool('ca/' + name, [(GMP + ':ca/' + name, 1, 'rigid')])
    wjson('data/%s/worldgen/structure/%s.json' % (GMP, name), {
        'type': 'minecraft:jigsaw', 'biomes': tag, 'max_distance_from_center': 64, 'size': 1, 'spawn_overrides': {},
        'start_pool': p, 'use_expansion_hack': False, 'project_start_to_heightmap': 'WORLD_SURFACE_WG',
        'start_height': {'absolute': -zg}, 'step': 'surface_structures', 'terrain_adaptation': 'none'})
wjson('data/%s/worldgen/structure_set/ca_ruins.json' % GMP, {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400917, 'separation': 96, 'spacing': 256, 'spread_type': 'triangular'},
    'structures': [{'structure': GMP + ':' + n, 'weight': 1} for n, _, _, _ in ca_list]})
GM_REPORT['ca_ruins'] = ['%s (%s)' % (n, rl) for n, _, _, rl in ca_list]


# ---------------------------------------------------------------- wall cross-sections
def section(path):
    head, rules, layers = tml_parse(path)
    layers = [lay for lay in layers if lay]
    H = max(len(lay) for lay in layers)
    W = max(len(r) for lay in layers for r in lay)
    return head, rules, layers, H, W


def section_cell(rules, layers, H, col, y, along, pickers):
    lay = layers[along % len(layers)]
    row = H - 1 - y
    if row >= len(lay) or col >= len(lay[row]):
        return None
    v = lay[row][col]
    if v == 0:
        return (AIR, None)
    if v not in pickers:
        return None
    return pickers[v]()


def make_pickers(rules, rng):
    return {k: picker(r, rng) for k, r in rules.items()}


# ---------------------------------------------------------------- Great Walls
wall_list = []
for fn in sorted(os.listdir(GM + '/greatwall')):
    if not fn.endswith('.tml'):
        continue
    style = snake(fn[:-4])
    head, rules, layers, H, W = section(GM + '/greatwall/' + fn)
    if 'Hell' in head.get('biomes', ''):
        REPORT.setdefault('gm_skipped', []).append(style + ' (Nether wall)')
        continue
    wrng = random.Random(style)
    pk = make_pickers(rules, wrng)
    spec = tower_spec(head)
    trule = tower_rule_of(spec, rules)
    tmat = picker(trule, wrng, solid=True)
    tkind = stair_kind(base_of(trule, wrng)[0])
    walk = int(head.get('walk_height', H - 2) or H - 2)
    N = '%s:wall/%s' % (GMP, style)
    nxt = '%s:wall/%s/next' % (GMP, style)
    hw = W // 2

    def segment(L, key):
        P = Piece()
        for z in range(L):
            for col in range(W):
                for y in range(H):
                    c = section_cell(rules, layers, H, col, y, z, pk)
                    if c:
                        P.set((col, y, z), c[0], c[1])
        for z in (0, L - 1):
            if (hw, 0, z) not in P.g or P.g[(hw, 0, z)][0] == 'minecraft:air':
                P.set((hw, 0, z), *tmat())
        P.jig((hw, 0, 0), 'north', N, N, nxt, 5)
        P.jig((hw, 0, L - 1), 'south', N, N, nxt, 5)
        return P.write('wall/%s/%s' % (style, key))

    def tower(key, outs):
        circ = wrng.random() < spec['circ']
        lo, hi, hlo, hhi = spec['ci' if circ else 'sq']
        S = max(W + 2, wrng.randint(lo, hi))
        if S % 2 == 0:
            S += 1
        Ht = max(wrng.randint(hlo, hhi), H + 3)
        roof = wrng.choice(spec['ci_roofs' if circ else 'sq_roofs'])
        P = Piece()
        dy = max(1, walk - 1)
        sp = spawner_token(spec['spawner'], wrng)
        build_tower(P, S, Ht, tmat, roof, tkind, wrng, circular=circ,
                    doors=[(f, dy) for f in outs] + [(outs[0], 1)], spawner=sp,
                    chest='minecraft:chests/village/village_weaponsmith' if wrng.random() < 0.5 else None)
        cells = footprint(S, circ)[0]
        for f in outs:
            x, z = side_cell(cells, S, f)
            P.jig((x, 0, z), f, N, N, nxt, 5)
        return P.write('wall/%s/%s' % (style, key))

    seg16 = segment(16, 'seg16')
    seg9 = segment(9, 'seg9')
    t_straight = [tower('tower_straight_%d' % i, ['north', 'south']) for i in range(2)]
    t_turn = [tower('tower_turn_%d' % i, ['north', 'east']) for i in range(2)]
    t_end = tower('tower_end', ['north'])
    end = pool('wall/%s/end' % style, [(t_end, 1, 'rigid')])
    pool('wall/%s/next' % style, [(seg16, 10, 'terrain_matching'), (seg9, 4, 'terrain_matching')] +
         [(t, 1, 'rigid') for t in t_straight] + [(t, 1, 'rigid') for t in t_turn], fallback=end)
    start = pool('wall/%s/start' % style, [(t, 1, 'rigid') for t in t_straight])
    tag = biome_tag('wall_' + style, gm_biomes(head, ['#minecraft:is_overworld']))
    wjson('data/%s/worldgen/structure/wall_%s.json' % (GMP, style), {
        'type': 'minecraft:jigsaw', 'biomes': tag, 'max_distance_from_center': 128, 'size': 14, 'spawn_overrides': {},
        'start_pool': start, 'use_expansion_hack': False, 'project_start_to_heightmap': 'WORLD_SURFACE_WG',
        'start_height': {'absolute': 0}, 'step': 'surface_structures', 'terrain_adaptation': 'beard_thin'})
    wall_list.append((style, max(1, min(10, int(head.get('weight', '1') or 1)))))
wjson('data/%s/worldgen/structure_set/great_walls.json' % GMP, {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400918, 'separation': 160, 'spacing': 384, 'spread_type': 'triangular'},
    'structures': [{'structure': '%s:wall_%s' % (GMP, s), 'weight': w} for s, w in wall_list]})
GM_REPORT['great_walls'] = [s for s, _ in wall_list]


# ---------------------------------------------------------------- city buildings
def tml_building_piece(name):
    """A converted TML building with a jigsaw at the middle of its front (its last row), ground level."""
    size, grid, bents, ents, embed, weight = GM_GRIDS[name]
    w, h, l = size
    P = Piece()
    for p, v in grid.items():
        P.g[p] = list(v)
    P.be.update(bents)
    P.ents = list(ents)
    jy = max(embed, 1) - 1
    if jy >= h:
        jy = 0
    pos = (w // 2, jy, l - 1)
    if pos not in P.g:
        P.set(pos, ('minecraft:cobblestone', {}))
    P.jig(pos, 'south', BUILDING, BUILDING, 'minecraft:empty')
    return P.write('city_building/' + name), weight


CITY_BUILDINGS = {}


def city_building(name):
    if name not in CITY_BUILDINGS:
        CITY_BUILDINGS[name] = tml_building_piece(name) if name in GM_GRIDS else None
    return CITY_BUILDINGS[name]


def house(key, spec, rules, rng, underground):
    trule = tower_rule_of(spec, rules)
    mat = picker(trule, rng, solid=True)
    base = base_of(trule, rng)[0]
    circ = rng.random() < spec['circ']
    lo, hi, hlo, hhi = spec['ci' if circ else 'sq']
    S = rng.randint(max(5, lo), max(5, hi))
    Ht = rng.randint(max(4, hlo), max(4, hhi))
    roof = rng.choice(spec['ci_roofs' if circ else 'sq_roofs'])
    P = Piece()
    sp = spawner_token(spec['spawner'], rng) if rng.random() < spec['mob_p'] else None
    cells = build_tower(P, S, Ht, mat, roof, roof_kind_for(base), rng, circular=circ, floors_every=4,
                        spawner=sp, chest='minecraft:chests/village/village_plains_house' if rng.random() < 0.6 else None,
                        furniture=spec['furniture'] or True, house_door='south' if spec['doors'] or True else None)
    x, z = side_cell(cells, S, 'south')
    if underground:  # a clear space before the door
        for y in (1, 2):
            P.air((x, y, z + 1))
    P.jig((x, 0, z), 'south', BUILDING, BUILDING, 'minecraft:empty')
    return P.write(key)


def road_picker(road_row, rules, rng):
    pks = make_pickers(rules, rng)

    def at(col):
        v = road_row[col] if col < len(road_row) else (road_row[len(road_row) // 2] if road_row else 1)
        r = pks.get(v, lambda: None)() if v else None
        if not r or r[0][0] == 'minecraft:air':
            return (('minecraft:cobblestone', {}), None) if not road_row else (base_of(rules.get(road_row[len(road_row) // 2]), rng), None)
        return r
    return at


def street_spec(path):
    head, rules, layers = tml_parse(path)
    layers = [lay for lay in layers if lay]
    row = layers[0][-1] if layers else [1, 1, 1, 1, 1]
    return dict(head=head, rules=rules, road=row, W=len(row), spec=tower_spec(head),
                buildings=[snake(b.strip()[:-4].replace('-p', '').replace('-', '_'))
                           for b in head.get('building_templates', 'NONE').split(',') if b.strip().endswith('.tml')])


def find_tml(name):
    for sub in ('walledcity/streets', 'walledcity', 'greatwall'):
        p = os.path.join(GM, sub, name)
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------- walled and underground cities
R = 48           # from the city's middle to the inside face of its wall
A_SPLIT = [(6, 19), (20, 33), (34, 47)]
city_list = []
for fn in sorted(os.listdir(GM + '/walledcity')):
    if not fn.endswith('.tml'):
        continue
    cname = snake(fn[:-4].replace('-', '_'))
    head, rules, layers, H, T = section(GM + '/walledcity/' + fn)
    if 'Hell' in head.get('biomes', ''):
        REPORT.setdefault('gm_skipped', []).append(cname + ' (Nether city)')
        continue
    if 'humans_plus' in cname:
        REPORT.setdefault('gm_skipped', []).append(cname + ' (same as its plain city, with Humans+ mobs)')
        continue
    under = 'Underground' in head.get('biomes', '')
    rng = random.Random(cname)
    streets = [s.strip() for s in head.get('street_templates', '').split(',') if s.strip().endswith('.tml')]
    spaths = [find_tml(s) for s in streets]
    spaths = [p for p in spaths if p]
    if under or not spaths:
        spaths = [GM + '/walledcity/' + fn] if under else [GM + '/walledcity/streets/CobblestoneStreet.tml']
    st = street_spec(spaths[0])
    if not under and not streets:
        # a city whose own spec is its street (no separate street templates)
        pass
    road = road_picker(st['road'], st['rules'], rng)
    sw = max(3, st['W'])
    hw = sw // 2
    G = hw + 2
    proj = 'rigid' if under else 'terrain_matching'
    clear_h = 5 if under else 3
    pfx = 'city/%s/' % cname
    N = lambda k: '%s:%s%s' % (GMP, pfx, k)

    def road_cell(P, x, z, col):
        r = road(col)
        P.set((x, 0, z), r[0], r[1])
        for y in range(1, clear_h + 1):
            P.air((x, y, z))
        if under and (x + z) % 7 == 0 and col == hw:
            P.set((x, clear_h, z), ('minecraft:lantern', {'hanging': 'true', 'waterlogged': 'false'}))

    # buildings pool: TML buildings of the streets and the city, generated houses, side streets
    bl = []
    for sp in spaths:
        bl += street_spec(sp)['buildings']
    bl += [snake(b.strip()[:-4].replace('-p', '').replace('-', '_')) for b in head.get('building_templates', 'NONE').split(',') if b.strip().endswith('.tml')]
    els = []
    for b in sorted(set(bl)):
        cb = city_building(b)
        if cb:
            els.append((cb[0], cb[1] + 1, 'rigid'))
    for i in range(8):
        sp = street_spec(rng.choice(spaths))
        els.append((house(pfx + 'house_%d' % i, sp['spec'], sp['rules'], rng, under), 3, 'rigid'))
    # side street: in from its front, buildings on both sides and at its end
    P = Piece()
    for z in range(16):
        for x in range(-hw, hw + 1):
            road_cell(P, x, z, x + hw)
    P.jig((0, 0, 15), 'south', BUILDING, BUILDING, 'minecraft:empty')
    for z in (3, 10):
        P.jig((-hw, 0, z), 'west', BUILDING, BUILDING, N('buildings'))
        P.jig((hw, 0, z), 'east', BUILDING, BUILDING, N('buildings'))
    P.jig((0, 0, 0), 'north', BUILDING, BUILDING, N('buildings'))
    els.append((P.write(pfx + 'side_street'), 5, proj))
    els.append((None, 2, None))
    pool(pfx + 'buildings', els)

    # plaza
    P = Piece()
    for x in range(-5, 6):
        for z in range(-5, 6):
            road_cell(P, x, z, hw)
    P.set((0, 0, 0), ('minecraft:water', {'level': '0'}))
    for dx in (-1, 0, 1):
        for dz in (-1, 0, 1):
            if dx or dz:
                P.set((dx, 1, dz), base_of(st['rules'].get(st['road'][hw]) if st['road'] else None, rng))
    for cx_, cz_ in ((-4, -4), (4, -4), (-4, 4), (4, 4)):
        P.set((cx_, 1, cz_), ('minecraft:oak_fence', {}))
        P.set((cx_, 2, cz_), ('minecraft:lantern', {'hanging': 'false', 'waterlogged': 'false'}))
    for f, (x, z) in (('north', (0, -5)), ('south', (0, 5)), ('east', (5, 0)), ('west', (-5, 0))):
        P.jig((x, 0, z), f, N('a1'), N('a1'), N('a1'), 10)
    plaza = P.write(pfx + 'plaza')

    walls = not under and H >= 4
    # the street to the north gate (the game turns it for the other three)
    for k, (a, b) in enumerate(A_SPLIT, 1):
        P = Piece()
        for z in range(-b, -a + 1):
            for x in range(-hw, hw + 1):
                road_cell(P, x, z, x + hw)
        P.jig((0, 0, -a), 'south', N('a%d' % k), N('a%d' % k), 'minecraft:empty', 10)
        nk = N('a%d' % (k + 1)) if k < len(A_SPLIT) else N('gate')
        if k < len(A_SPLIT) or walls:
            P.jig((0, 0, -b), 'north', nk, nk, nk, 10)
        else:
            P.jig((0, 0, -b), 'north', BUILDING, BUILDING, N('buildings'))
        for z in (-a - 3, -b + 3):
            P.jig((-hw, 0, z), 'west', BUILDING, BUILDING, N('buildings'))
            P.jig((hw, 0, z), 'east', BUILDING, BUILDING, N('buildings'))
        pool(pfx + 'a%d' % k, [(P.write(pfx + 'a%d' % k), 1, proj)])

    if walls:
        pk = make_pickers(rules, rng)
        spec = tower_spec(head)
        trule = tower_rule_of(spec, rules)
        tmat = picker(trule, rng, solid=True)
        tkind = stair_kind(base_of(trule, rng)[0])
        walk = int(head.get('walk_height', H - 2) or H - 2)
        z_out, z_in = -(R + T - 1), -R
        zc = (z_out + z_in) // 2

        def wall_cells(P, x0, x1, gate=False):
            for x in range(x0, x1 + 1):
                for z in range(z_out, z_in + 1):
                    col = z - z_out
                    for y in range(H):
                        if gate and -hw <= x <= hw and y <= min(H - 2, 5):
                            if y == 0:
                                r = road(x + hw)
                                P.set((x, 0, z), r[0], r[1])
                            else:
                                P.air((x, y, z))
                            continue
                        c = section_cell(rules, layers, H, col, y, x, pk)
                        if c:
                            P.set((x, y, z), c[0], c[1])
                if (x, 0, zc) not in P.g or P.g[(x, 0, zc)][0] == 'minecraft:air':
                    P.set((x, 0, zc), *tmat())

        P = Piece()
        wall_cells(P, -G, G, gate=True)
        P.jig((0, 0, z_in), 'south', N('gate'), N('gate'), 'minecraft:empty', 10)
        P.jig((G, 0, zc), 'east', N('cw1'), N('cw1'), N('cw1'), 10)
        P.jig((-G, 0, zc), 'west', N('ccw1'), N('ccw1'), N('ccw1'), 10)
        pool(pfx + 'gate', [(P.write(pfx + 'gate'), 1, proj)])
        chunks = []
        x = G + 1
        while x <= R - 1:
            chunks.append((x, min(R - 1, x + 15)))
            x += 16
        for i, (a, b) in enumerate(chunks, 1):
            P = Piece()
            wall_cells(P, a, b)
            P.jig((a, 0, zc), 'west', N('cw%d' % i), N('cw%d' % i), 'minecraft:empty', 10)
            nk = N('cw%d' % (i + 1)) if i < len(chunks) else N('corner')
            P.jig((b, 0, zc), 'east', nk, nk, nk, 10)
            pool(pfx + 'cw%d' % i, [(P.write(pfx + 'cw%d' % i), 1, proj)])
            P = Piece()
            wall_cells(P, -b, -a)
            P.jig((-a, 0, zc), 'east', N('ccw%d' % i), N('ccw%d' % i), 'minecraft:empty', 10)
            if i < len(chunks):
                P.jig((-b, 0, zc), 'west', N('ccw%d' % (i + 1)), N('ccw%d' % (i + 1)), N('ccw%d' % (i + 1)), 10)
            pool(pfx + 'ccw%d' % i, [(P.write(pfx + 'ccw%d' % i), 1, proj)])
        # corner tower: covers x in [R, R+S-1], z in [-(R+S-1), -R]
        lo, hi, hlo, hhi = spec['sq']
        S = max(T, min(T + 6, rng.randint(lo, hi)))
        Ht = max(rng.randint(hlo, hhi), H + 4)
        P = Piece()
        sp = spawner_token(spec['spawner'], rng)
        build_tower(P, S, Ht, tmat, rng.choice(spec['sq_roofs']), tkind, rng,
                    doors=[('west', max(1, walk - 1)), ('south', max(1, walk - 1)), ('west', 1)], spawner=sp,
                    chest='minecraft:chests/village/village_weaponsmith')
        Q = Piece()  # move into city coordinates
        for (x, y, z), v in P.g.items():
            Q.g[(R + x, y, -(R + S - 1) + z)] = v
        for (x, y, z), v in P.be.items():
            Q.be[(R + x, y, -(R + S - 1) + z)] = v
        Q.ents = [(R + x, y, -(R + S - 1) + z, e) for x, y, z, e in P.ents]
        Q.jig((R, 0, zc), 'west', N('corner'), N('corner'), 'minecraft:empty', 10)
        pool(pfx + 'corner', [(Q.write(pfx + 'corner'), 1, 'rigid')])

    start = pool(pfx + 'start', [(plaza, 1, proj)])
    tag = biome_tag('city_' + cname, ['#minecraft:is_overworld'] if under else gm_biomes(head))
    sj = {'type': 'minecraft:jigsaw', 'biomes': tag, 'max_distance_from_center': 96, 'size': 12, 'spawn_overrides': {},
          'start_pool': start, 'use_expansion_hack': False}
    if under:
        sj.update(start_height={'type': 'minecraft:uniform', 'min_inclusive': {'absolute': -40}, 'max_inclusive': {'absolute': -12}},
                  step='underground_structures', terrain_adaptation='none')
    else:
        sj.update(project_start_to_heightmap='WORLD_SURFACE_WG', start_height={'absolute': 0},
                  step='surface_structures', terrain_adaptation='beard_thin')
    wjson('data/%s/worldgen/structure/city_%s.json' % (GMP, cname), sj)
    city_list.append((cname, under, max(1, min(10, int(head.get('weight', '1') or 1)))))

wjson('data/%s/worldgen/structure_set/walled_cities.json' % GMP, {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400919, 'separation': 192, 'spacing': 448, 'spread_type': 'triangular'},
    'structures': [{'structure': '%s:city_%s' % (GMP, c), 'weight': w} for c, u, w in city_list if not u]})
wjson('data/%s/worldgen/structure_set/underground_cities.json' % GMP, {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400920, 'separation': 20, 'spacing': 56},
    'structures': [{'structure': '%s:city_%s' % (GMP, c), 'weight': w} for c, u, w in city_list if u]})
GM_REPORT['walled_cities'] = [c for c, u, w in city_list if not u]
GM_REPORT['underground_cities'] = [c for c, u, w in city_list if u]
