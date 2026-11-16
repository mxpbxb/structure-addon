"""Builds the Structure Add-on content mod (Horizon .hmod source folder) from four Minecraft mods:
Underground Biomes Constructs (stone blocks + strata blobs), Recurrent Complex (structures),
Wild Caves (cave features, miner camp) and Ancient Structures (culture buildings)."""
import sys, os, json, re, shutil, zipfile, collections, zlib, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nbt
import blocks as B

P = os.path.expanduser('~/horizon-dev/structures-port')
J = P + '/jars'
STAGE = P + '/stage'
OUT = P + '/content'
MODID = 'structure_addon'
REPORT = collections.OrderedDict()

if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)


def wjson(rel, obj):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', newline='\n') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')


def snake(s):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s)
    return re.sub(r'[^a-z0-9_]', '_', s.lower())


# ------------------------------------------------------------------ templates
def write_template(rel, size, grid, bents, ents=()):
    """grid: (x,y,z) -> [name, props]; bents: (x,y,z) -> nbt compound (tagged dict);
    ents: (x,y,z, entity id) for mobs standing in the template."""
    B.connect(grid)
    palette = []
    pindex = {}
    blist = []
    order = sorted(grid.items(), key=lambda kv: (not B.is_full(kv[0 + 1][0]), kv[0] in bents, kv[0][1], kv[0][0], kv[0][2]))
    for pos, (name, props) in order:
        key = (name, tuple(sorted(props.items())))
        if key not in pindex:
            pindex[key] = len(palette)
            e = {'id': nbt.S(name)}
            if props:
                e['properties'] = nbt.C({k: nbt.S(v) for k, v in sorted(props.items())})
            palette.append(e)
        b = {'pos': nbt.L(nbt.INT, list(pos)), 'state': nbt.I(pindex[key])}
        if pos in bents:
            b['nbt'] = nbt.C(bents[pos])
        blist.append(b)
    root = {
        'size': nbt.L(nbt.INT, list(size)),
        'entities': nbt.L(nbt.COMPOUND, [
            {'pos': nbt.L(nbt.DOUBLE, [x + 0.5, float(y), z + 0.5]), 'blockPos': nbt.L(nbt.INT, [x, y, z]),
             'nbt': nbt.C({'id': nbt.S(eid), 'PersistenceRequired': (nbt.BYTE, 1)})} for x, y, z, eid in ents]),
        'blocks': nbt.L(nbt.COMPOUND, blist),
        'palette': nbt.L(nbt.COMPOUND, palette),
        'DataVersion': nbt.I(5023),
    }
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    nbt.dump(p, root)
    return len(blist)


def load_nbt_lenient(path):
    raw = open(path, 'rb').read()
    try:
        return nbt.load_bytes(raw)
    except Exception:
        # gzip with a bad checksum: inflate the raw deflate stream and ignore the trailer
        flg = raw[3]; off = 10
        if flg & 4: off += 2 + int.from_bytes(raw[off:off + 2], 'little')
        if flg & 8: off = raw.index(b'\0', off) + 1
        if flg & 16: off = raw.index(b'\0', off) + 1
        if flg & 2: off += 2
        d = zlib.decompressobj(-15).decompress(raw[off:])
        import io
        f = io.BytesIO(d); t = f.read(1)[0]; nbt._rs(f)
        return nbt._read(f, t)


def convert_items(items_tag):
    """1.20 Items list -> 26.3 (count int, no tag); drops foreign items."""
    et, items = items_tag[1]
    out = []
    for it in items:
        iid = it.get('id', (nbt.STRING, ''))[1]
        if not isinstance(iid, str) or not iid.startswith('minecraft:'):
            continue
        c = {'Slot': it.get('Slot', (nbt.BYTE, 0)), 'id': nbt.S(iid),
             'count': nbt.I(int(it.get('Count', (nbt.BYTE, 1))[1] or it.get('count', (nbt.INT, 1))[1]))}
        out.append(c)
    return nbt.L(nbt.COMPOUND, out)


ITEM_OK = set()  # vanilla item ids (filled from facts? items aren't there; accept any minecraft id)


def convert_be(tag, state_name):
    """Old block entity compound -> minimal 26.3 compound, or None."""
    bid = tag.get('id', (nbt.STRING, ''))[1]
    if not isinstance(bid, str):
        return None
    bid = bid if ':' in bid else 'minecraft:' + snake(bid)
    out = {'id': nbt.S(bid)}
    if 'LootTable' in tag:
        lt = tag['LootTable'][1]
        if lt.startswith('minecraft:') or lt.startswith('ancientstructures:') or lt.startswith('wildcaves:'):
            out['LootTable'] = nbt.S(lt)
    if 'Items' in tag and bid in ('minecraft:chest', 'minecraft:trapped_chest', 'minecraft:barrel', 'minecraft:furnace',
                                  'minecraft:dispenser', 'minecraft:dropper', 'minecraft:hopper', 'minecraft:smoker',
                                  'minecraft:blast_furnace', 'minecraft:shulker_box', 'minecraft:chiseled_bookshelf'):
        out['Items'] = convert_items(tag['Items'])
    if bid == 'minecraft:mob_spawner':
        ent = None
        sd = tag.get('SpawnData')
        if sd and 'entity' in sd[1]:
            ent = sd[1]['entity'][1].get('id', (0, None))[1]
        if ent and ent.startswith('minecraft:'):
            out['SpawnData'] = nbt.C({'entity': nbt.C({'id': nbt.S(ent)})})
        else:
            return None
    return out


# ------------------------------------------------------------------ biomes
BIOMES = set(x[:-5] for x in os.listdir(P + '/vanilla263/data/minecraft/worldgen/biome'))
NETHER_END = {'basalt_deltas', 'crimson_forest', 'nether_wastes', 'soul_sand_valley', 'warped_forest', 'end_barrens',
              'end_highlands', 'end_midlands', 'small_end_islands', 'the_end', 'the_void'}
OCEANS = {b for b in BIOMES if 'ocean' in b}
CAVES = {'deep_dark', 'dripstone_caves', 'lush_caves', 'sulfur_caves'}
LAND = BIOMES - NETHER_END - OCEANS - CAVES - {'river', 'frozen_river'}
TOK = {
    'PLAINS': {'plains', 'sunflower_plains', 'meadow', 'snowy_plains'},
    'FOREST': {'forest', 'flower_forest', 'birch_forest', 'old_growth_birch_forest', 'dark_forest', 'dappled_forest',
               'taiga', 'snowy_taiga', 'old_growth_pine_taiga', 'old_growth_spruce_taiga', 'grove', 'windswept_forest',
               'cherry_grove', 'pale_garden', 'jungle', 'sparse_jungle', 'bamboo_jungle', 'wooded_badlands'},
    'MOUNTAIN': {'windswept_hills', 'windswept_gravelly_hills', 'windswept_forest', 'jagged_peaks', 'frozen_peaks',
                 'stony_peaks', 'snowy_slopes', 'grove', 'meadow', 'cherry_grove'},
    'HILLS': {'windswept_hills', 'windswept_gravelly_hills', 'windswept_forest', 'windswept_savanna', 'meadow',
              'cherry_grove', 'wooded_badlands', 'savanna_plateau'},
    'SWAMP': {'swamp', 'mangrove_swamp'},
    'SAVANNA': {'savanna', 'savanna_plateau', 'windswept_savanna'},
    'SANDY': {'desert', 'beach', 'badlands', 'eroded_badlands', 'wooded_badlands'},
    'DESERT': {'desert'},
    'HOT': {'desert', 'badlands', 'eroded_badlands', 'wooded_badlands', 'savanna', 'savanna_plateau', 'windswept_savanna',
            'jungle', 'sparse_jungle', 'bamboo_jungle', 'mangrove_swamp'},
    'DRY': {'desert', 'badlands', 'eroded_badlands', 'wooded_badlands', 'savanna', 'savanna_plateau', 'windswept_savanna'},
    'JUNGLE': {'jungle', 'sparse_jungle', 'bamboo_jungle'},
    'RIVER': {'river', 'frozen_river'}, 'BEACH': {'beach', 'snowy_beach', 'stony_shore'},
    'OCEAN': OCEANS, 'WATER': OCEANS | {'river', 'frozen_river'},
    'WASTELAND': {'badlands', 'eroded_badlands', 'desert'}, 'MESA': {'badlands', 'eroded_badlands', 'wooded_badlands'},
    'MUSHROOM': {'mushroom_fields'},
    'SNOWY': {'snowy_plains', 'ice_spikes', 'snowy_taiga', 'snowy_slopes', 'frozen_peaks', 'jagged_peaks', 'grove', 'snowy_beach'},
    'COLD': {'snowy_plains', 'ice_spikes', 'snowy_taiga', 'snowy_slopes', 'frozen_peaks', 'jagged_peaks', 'grove',
             'taiga', 'old_growth_pine_taiga', 'old_growth_spruce_taiga', 'windswept_hills', 'windswept_gravelly_hills', 'stony_peaks'},
    'CONIFEROUS': {'taiga', 'snowy_taiga', 'old_growth_pine_taiga', 'old_growth_spruce_taiga', 'grove'},
    'SPOOKY': {'dark_forest', 'pale_garden', 'swamp'}, 'MAGICAL': {'flower_forest', 'cherry_grove', 'mushroom_fields'},
    'DENSE': {'jungle', 'bamboo_jungle', 'dark_forest', 'pale_garden'}, 'WET': {'swamp', 'mangrove_swamp', 'jungle', 'bamboo_jungle'},
    'SPARSE': {'plains', 'savanna', 'desert', 'snowy_plains', 'sparse_jungle'}, 'LUSH': {'jungle', 'flower_forest', 'lush_caves'},
    'NETHER': set(), 'END': set(), 'VOID': set(),
}


def rc_biomes(gen_biomes):
    inc, exc = set(), set()
    for e in gen_biomes:
        expr = e.get('biomes', '')
        w = e.get('weight', 1.0)
        parts = [p.strip() for p in re.split(r'[|]', expr)]
        s = set()
        for part in parts:
            toks = re.findall(r'(!?)\$([A-Z_]+)', part)
            cur = None
            for neg, t in toks:
                ts = TOK.get(t, LAND)
                if neg:
                    ts = LAND - ts
                cur = set(ts) if cur is None else cur & ts
            if cur:
                s |= cur
        if w == 0:
            exc |= s
        else:
            inc |= s
    res = (inc - exc) & BIOMES
    return sorted(res) or sorted(LAND)


# ------------------------------------------------------------------ Recurrent Complex
RC = J + '/rc/x/assets/reccomplex/structures/active/structures'
NOGEN_BIOMES = {  # RC structures shipped without natural generation info: give them a home
    'BigClockworkSite': ['$PLAINS', '$SAVANNA'], 'SmallClockworkSite': ['$PLAINS', '$SAVANNA', '$FOREST'],
    'DinosaurSkeleton': ['$SANDY', '$SAVANNA'], 'PirateChest': ['$BEACH'], 'ShrineSmallAir': ['$MOUNTAIN', '$HILLS'],
    'ShrineSmallEarth': ['$FOREST', '$PLAINS'], 'ShrineSmallFire': ['$SANDY', '$SAVANNA'],
    'ShrineSmallWater': ['$SWAMP', '$BEACH'], 'TemplePyramid': ['$JUNGLE'], 'TribalJungleHead': ['$JUNGLE'],
}
MOBS = {'PigZombie': 'zombified_piglin', 'LavaSlime': 'magma_cube', 'CaveSpider': 'cave_spider', 'EntityHorse': 'horse',
        'VillagerGolem': 'iron_golem', 'SnowMan': 'snow_golem', 'Ozelot': 'ocelot', 'MushroomCow': 'mooshroom'}
RC_LOOT = {'decoration': 'minecraft:chests/village/village_plains_house', 'adventure': 'minecraft:chests/simple_dungeon',
           'rare': 'minecraft:chests/stronghold_corridor', 'bedrock': 'minecraft:chests/abandoned_mineshaft',
           'frequent': 'minecraft:chests/village/village_plains_house', 'ultrarare': 'minecraft:chests/stronghold_corridor'}
PLANTISH = re.compile(r'(grass|fern|flower|bush|sapling|mushroom|air|snow|vine|tall)')


def rc_unpack(bc):
    w, h, l = bc['width'], bc['height'], bc['length']
    n = w * h * l
    blk = bc['blocks']
    if 'blockBytes' in blk:
        ids = list(blk['blockBytes'][:n])
    else:
        c = blk['blocksCompressed']
        data, bl = c['data_bytes'], c['data_bitLength']
        ids = []
        bits = int.from_bytes(data, 'little')
        mask = (1 << bl) - 1
        for k in range(n):
            ids.append((bits >> (k * bl)) & mask)
    meta = list(bc['metadata'][:n])
    return w, h, l, ids, meta


rc_structs = []
for root, dirs, files in os.walk(RC):
    for fn in sorted(files):
        if not fn.endswith('.rcst'):
            continue
        base = fn[:-5]
        rel = os.path.relpath(os.path.join(root, fn), RC)
        z = zipfile.ZipFile(os.path.join(root, fn))
        js = json.loads(z.read('structure.json'))
        gis = [g for g in js.get('generationInfos', []) if g['type'] == 'natural']
        if base in ('StoneMaze', 'StoneMazeSmall'):
            REPORT.setdefault('rc_skipped', []).append(base + ' (maze is generated by RC code; only an empty shell is stored)')
            continue
        if '/' in rel:
            REPORT.setdefault('rc_skipped', []).append(base + ' (maze/village piece, needs RC code)')
            continue
        if not gis and base not in NOGEN_BIOMES:
            REPORT.setdefault('rc_skipped', []).append(base + ' (no natural generation)')
            continue
        r = nbt.plain(nbt.COMPOUND, nbt.load_bytes(z.read('worldData.nbt')))
        bc = r['blockCollection']
        w, h, l, ids, meta = rc_unpack(bc)
        mapping = bc['mapping']
        raw = {}
        for z_ in range(l):
            for y in range(h):
                for x in range(w):
                    i = (z_ * h + y) * w + x
                    raw[(x, y, z_)] = (mapping[ids[i]] if ids[i] < len(mapping) else 'minecraft:air', meta[i])
        grid = {}
        solid = 0
        for pos, (name, m) in raw.items():
            if name == 'reccomplex:negativeSpace':
                if m == 1:
                    grid[pos] = ['minecraft:air', {}]
                continue
            if name == 'reccomplex:naturalFloor':
                above = raw.get((pos[0], pos[1] + 1, pos[2]), ('minecraft:air', 0))[0]
                top = above in ('minecraft:air', 'reccomplex:negativeSpace') or PLANTISH.search(above)
                grid[pos] = ['minecraft:grass_block', {'snowy': 'false'}] if top else ['minecraft:dirt', {}]
                solid += 1
                continue
            if name == 'reccomplex:generic_solid':
                grid[pos] = ['minecraft:stone', {}]; solid += 1; continue
            if name.startswith('reccomplex:'):
                grid[pos] = ['minecraft:air', {}]; continue
            if name == 'minecraft:skull':
                grid[pos] = ['minecraft:skeleton_skull', {}]; continue
            st = B.legacy(name, m)
            if st is None:
                REPORT.setdefault('rc_unknown_blocks', collections.Counter())[name] += 1
                grid[pos] = ['minecraft:air', {}]
                continue
            grid[pos] = [st[0], dict(st[1])]
            if st[0] != 'minecraft:air':
                solid += 1
        if solid < 40:
            REPORT.setdefault('rc_skipped', []).append(base + ' (empty: generated by code)')
            continue
        gi = gis[0]['generationInfo'] if gis else {'generationCategory': 'decoration',
                                                    'generationY': {'selectionMode': 'surface', 'minY': 0, 'maxY': 0},
                                                    'generationBiomes': [{'biomes': ' | '.join(NOGEN_BIOMES[base])}]}
        cat = gi.get('generationCategory', 'decoration')
        gy = gi.get('generationY', {})
        mode = gy.get('selectionMode', 'surface')
        bents = {}
        for te in r.get('tileEntities', []):
            pos = (te['x'], te['y'], te['z'])
            if pos not in grid:
                continue
            tid = te.get('id')
            if tid in ('Chest', 'TrapChest'):
                bents[pos] = {'id': nbt.S('minecraft:trapped_chest' if tid == 'TrapChest' else 'minecraft:chest'),
                              'LootTable': nbt.S(RC_LOOT['bedrock' if mode == 'bedrock' else cat])}
            elif tid == 'MobSpawner':
                e = te.get('EntityId', 'Zombie')
                e = MOBS.get(e, snake(e))
                if e:
                    bents[pos] = {'id': nbt.S('minecraft:mob_spawner'),
                                  'SpawnData': nbt.C({'entity': nbt.C({'id': nbt.S('minecraft:' + e)})})}
        name = snake(base)
        n = write_template('data/reccomplex/structure/%s.nbt' % name, (w, h, l), grid, bents)
        biomes = rc_biomes(gi.get('generationBiomes', []))
        rc_structs.append(dict(name=name, mode=mode, minY=gy.get('minY', 0), maxY=gy.get('maxY', 0), biomes=biomes,
                               cat=cat, size=(w, h, l), blocks=n))

for s in rc_structs:
    nm = s['name']
    wjson('data/reccomplex/tags/worldgen/biome/has_structure/%s.json' % nm, {'values': ['minecraft:' + b for b in s['biomes']]})
    wjson('data/reccomplex/worldgen/template_pool/%s.json' % nm, {
        'elements': [{'element': {'element_type': 'minecraft:single_pool_element', 'location': 'reccomplex:' + nm,
                                  'processors': 'minecraft:empty', 'projection': 'rigid'}, 'weight': 1}],
        'fallback': 'minecraft:empty'})
    st = {'type': 'minecraft:jigsaw', 'biomes': '#reccomplex:has_structure/' + nm, 'max_distance_from_center': 128,
          'size': 1, 'spawn_overrides': {}, 'start_pool': 'reccomplex:' + nm, 'use_expansion_hack': False}
    if s['mode'] == 'bedrock':
        lo, hi = -64 + min(s['minY'], s['maxY']), -64 + max(s['minY'], s['maxY'])
        st.update(step='underground_structures', terrain_adaptation='encapsulate',
                  start_height={'type': 'minecraft:uniform', 'min_inclusive': {'absolute': lo}, 'max_inclusive': {'absolute': hi}})
    else:
        st.update(step='surface_structures', terrain_adaptation='beard_thin', project_start_to_heightmap='WORLD_SURFACE_WG',
                  start_height={'absolute': int(s['minY'])})
    wjson('data/reccomplex/worldgen/structure/%s.json' % nm, st)

surf = [s for s in rc_structs if s['mode'] != 'bedrock']
under = [s for s in rc_structs if s['mode'] == 'bedrock']
CATW = {'decoration': 3, 'adventure': 2, 'rare': 1, 'frequent': 3, 'ultrarare': 1}
wjson('data/reccomplex/worldgen/structure_set/surface.json', {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400913, 'separation': 96, 'spacing': 256, 'spread_type': 'triangular'},
    'structures': [{'structure': 'reccomplex:' + s['name'], 'weight': CATW.get(s['cat'], 2)} for s in surf]})
wjson('data/reccomplex/worldgen/structure_set/underground.json', {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400914, 'separation': 8, 'spacing': 28},
    'structures': [{'structure': 'reccomplex:' + s['name'], 'weight': 1} for s in under]})
REPORT['rc_surface'] = [s['name'] for s in surf]
REPORT['rc_underground'] = [s['name'] for s in under]

# ------------------------------------------------------------------ Ancient Structures
ASD = STAGE + '/as_out/data/ancientstructures'
for sub in ('worldgen/structure', 'worldgen/template_pool'):
    for fn in os.listdir(ASD + '/' + sub):
        wjson('data/ancientstructures/%s/%s' % (sub, fn), json.load(open(ASD + '/' + sub + '/' + fn)))
for fn in os.listdir(ASD + '/worldgen/structure_set'):
    d = json.load(open(ASD + '/worldgen/structure_set/' + fn))
    d['placement']['spacing'] = 320
    d['placement']['separation'] = 128
    wjson('data/ancientstructures/worldgen/structure_set/' + fn, d)


def fix_tag(d):
    vals = []
    for v in d['values']:
        if isinstance(v, dict):
            v = v['id']
        ns = v.lstrip('#').split(':')[0]
        if ns in ('minecraft', 'ancientstructures', 'biomesoplenty', 'wildcaves', 'reccomplex'):
            if not v.startswith('#') and ns == 'minecraft' and v.split(':')[1] not in BIOMES:
                continue
            vals.append(v)
    return {'values': vals}


for root, dirs, files in os.walk(ASD + '/tags/worldgen/biome'):
    for fn in files:
        relp = os.path.relpath(os.path.join(root, fn), ASD)
        wjson('data/ancientstructures/' + relp, fix_tag(json.load(open(os.path.join(root, fn)))))


def fix_loot(d):
    def walk(x):
        if isinstance(x, dict):
            if 'entries' in x:
                ents = []
                for e in x['entries']:
                    nm = e.get('name')
                    if e.get('type', '').endswith('item') and nm and ':' in nm and not nm.startswith('minecraft:'):
                        continue
                    ents.append(walk(e))
                x['entries'] = ents
            return {k: walk(v) if k != 'entries' else v for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return walk(d)


for fn in os.listdir(ASD + '/loot_table/chest'):
    wjson('data/ancientstructures/loot_table/chest/' + fn, fix_loot(json.load(open(ASD + '/loot_table/chest/' + fn))))

as_counts = {}
for fn in sorted(os.listdir(J + '/as/x/data/ancientstructures/structures')):
    try:
        r = load_nbt_lenient(J + '/as/x/data/ancientstructures/structures/' + fn)
    except Exception as e:
        REPORT.setdefault('as_skipped', []).append('%s (file is corrupt in the jar: %s)' % (fn, e))
        stem = fn[:-4]
        for d in ('worldgen/structure', 'worldgen/template_pool', 'tags/worldgen/biome/has_structure'):
            pth = os.path.join(OUT, 'data/ancientstructures', d, stem + '.json')
            if os.path.exists(pth): os.remove(pth)
        for sfn in os.listdir(OUT + '/data/ancientstructures/worldgen/structure_set'):
            sp = OUT + '/data/ancientstructures/worldgen/structure_set/' + sfn
            d = json.load(open(sp))
            d['structures'] = [s for s in d['structures'] if s['structure'] != 'ancientstructures:' + stem]
            wjson('data/ancientstructures/worldgen/structure_set/' + sfn, d)
        continue
    p = nbt.plain(nbt.COMPOUND, r)
    pal = []
    for e in p['palette']:
        pal.append(B.map_any(e['Name'], e.get('Properties', {})))
    grid, bents = {}, {}
    for b in r['blocks'][1][1]:
        pos = tuple(b['pos'][1][1])
        st = pal[b['state'][1]]
        if st is None:
            grid[pos] = ['minecraft:air', {}]
            continue
        if st[0] == 'minecraft:structure_void':
            continue
        grid[pos] = [st[0], dict(st[1])]
        if 'nbt' in b:
            be = convert_be(b['nbt'][1], st[0])
            if be:
                bents[pos] = be
    size = p['size']
    as_counts[fn] = write_template('data/ancientstructures/structure/' + fn, size, grid, bents)
REPORT['as_structures'] = list(as_counts)

# ------------------------------------------------------------------ Generatormods (formivore)
# Its standalone buildings (TML templates from the Great Wall and Walled City packs) become single
# structures; the walls, cities, streets and cellular-automaton ruins are built by its code and are
# not ported.
GM = J + '/gm/config'
GM_LOOT = {'EASY': 'minecraft:chests/simple_dungeon', 'MEDIUM': 'minecraft:chests/abandoned_mineshaft',
           'HARD': 'minecraft:chests/stronghold_corridor', 'TOWER': 'minecraft:chests/village/village_weaponsmith',
           None: 'minecraft:chests/village/village_plains_house'}
GM_SPAWN = {'EASY': ['zombie', 'skeleton', 'spider'], 'MEDIUM': ['skeleton', 'zombie'], 'HARD': ['cave_spider', 'blaze'],
            'UPRIGHT': ['zombie', 'skeleton'], 'humansplus': ['zombie'], 'Zombie': ['zombie'], 'Skeleton': ['skeleton'],
            'Spider': ['spider'], 'Blaze': ['blaze'], 'PigZombie': ['zombified_piglin'], 'LavaSlime': ['magma_cube'],
            'Enderman': ['enderman'], 'Ghast': ['ghast'], 'CaveSpider': ['cave_spider']}
GM_PASSIVE = {'Villager': 'minecraft:villager', 'Pig': 'minecraft:pig', 'MushroomCow': 'minecraft:mooshroom'}


def legacy_num(bid, meta):
    s = B.FLAT_MAP.get(bid << 4 | (meta & 15))
    if s is None:
        s = next((B.FLAT_MAP[bid << 4 | m] for m in range(16) if (bid << 4 | m) in B.FLAT_MAP), None)
    if s is None or s[0] == '%%FILTER_ME%%':
        return None
    n, p = s
    return B.fix(B.POST13.get(n, n), p)


def tml_parse(path):
    head, rules, layers, cur = {}, {}, [], None
    for line in open(path, encoding='latin-1'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line == 'layer':
            cur = []
        elif line == 'endlayer':
            if cur:
                layers.append(cur)
            cur = None
        elif cur is not None:
            cur.append([int(v) if v.strip().lstrip('-').isdigit() else 0 for v in line.split(',')])
        elif '=' in line:
            k, v = line.split('=', 1)
            m = re.match(r'rule(\d+)$', k.strip())
            if m:
                f = [t.strip() for t in v.split('#')[0].split(',')]
                rules[int(m.group(1))] = (int(f[1]) if f[1].isdigit() else 100, [t for t in f[2:] if t])
            else:
                head[k.strip()] = v.strip()
    return head, rules, layers


def tml_token(tok, rng):
    """One rule token -> ('block', state, be) | ('entity', id) | ('void',)."""
    if tok == 'PRESERVE':
        return ('void',)
    if re.match(r'WALL_STAIR-(\d+)', tok):
        # The original places a stair only where the wall steps up or down, and leaves the walkway
        # open elsewhere; a template has one height, so the walkway stays open.
        return ('block', ('minecraft:air', {}), None)
    m = re.match(r'(\d+)(?:-(\d+))?(?:-(\w+))?$', tok)
    if not m:
        return ('void',)
    bid, meta, extra = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if bid == 0:
        return ('block', ('minecraft:air', {}), None)
    if bid == 52:
        if extra in GM_PASSIVE:
            return ('entity', GM_PASSIVE[extra])
        mob = rng.choice(GM_SPAWN.get(extra, ['zombie']))
        return ('block', ('minecraft:spawner', {}),
                {'id': nbt.S('minecraft:mob_spawner'), 'SpawnData': nbt.C({'entity': nbt.C({'id': nbt.S('minecraft:' + mob)})})})
    if bid > 175:
        return ('void',)
    st = legacy_num(bid, meta)
    if st is None:
        return ('void',)
    if bid in (54, 146):
        return ('block', st, {'id': nbt.S('minecraft:chest' if bid == 54 else 'minecraft:trapped_chest'),
                              'LootTable': nbt.S(GM_LOOT.get(extra, GM_LOOT[None]))})
    return ('block', st, None)


gm_files = {}
for sub in ('greatwall/buildings', 'walledcity/buildings', 'walledcity/streets/buildings'):
    d = os.path.join(GM, sub)
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if fn.endswith('.tml'):
            gm_files[snake(fn[:-4].replace('-p', '').replace('-', '_'))] = os.path.join(d, fn)
gm_structs = []
GM_GRIDS = {}
for name, path in sorted(gm_files.items()):
    if name.startswith('nether'):
        REPORT.setdefault('gm_skipped', []).append(name + ' (Nether building; its Nether city is built by code)')
        continue
    head, rules, layers = tml_parse(path)
    if not layers:
        continue
    rng = random.Random(name)
    h = len(layers)
    l = max(len(r) for r in layers)
    w = max(len(row) for r in layers for row in r)
    grid, bents, ents = {}, {}, []
    for y, layer in enumerate(layers):
        for z, row in enumerate(layer):
            for x, v in enumerate(row):
                if v == 0:
                    grid[(x, y, z)] = ['minecraft:air', {}]
                    continue
                rule = rules.get(v)
                if not rule or rng.randint(1, 100) > rule[0] or not rule[1]:
                    continue
                r = tml_token(rng.choice(rule[1]), rng)
                if r[0] == 'block':
                    grid[(x, y, z)] = [r[1][0], dict(r[1][1])]
                    if r[2]:
                        bents[(x, y, z)] = r[2]
                elif r[0] == 'entity':
                    grid[(x, y, z)] = ['minecraft:air', {}]
                    ents.append((x, y, z, r[1]))
    if sum(1 for v in grid.values() if v[0] != 'minecraft:air') < 10:
        REPORT.setdefault('gm_skipped', []).append(name + ' (empty)')
        continue
    embed = int(head.get('embed_into_distance', '1') or 1)
    GM_GRIDS[name] = ((w, h, l), {k: list(v) for k, v in grid.items()}, dict(bents), list(ents), embed,
                      max(1, min(5, int(head.get('weight', '1') or 1))))
    n = write_template('data/generatormods/structure/%s.nbt' % name, (w, h, l), grid, bents, ents)
    weight = max(1, min(10, int(head.get('weight', '1') or 1)))
    gm_structs.append(dict(name=name, embed=embed, under=h >= 8 and h - embed <= 2, weight=weight, size=(w, h, l), blocks=n))

SNOWY_GM = ['minecraft:' + b for b in sorted(TOK['SNOWY'])]
for s in gm_structs:
    nm = s['name']
    biomes = SNOWY_GM if nm.startswith('snow') else ['#minecraft:is_overworld']
    wjson('data/generatormods/tags/worldgen/biome/has_structure/%s.json' % nm, {'values': biomes})
    wjson('data/generatormods/worldgen/template_pool/%s.json' % nm, {
        'elements': [{'element': {'element_type': 'minecraft:single_pool_element', 'location': 'generatormods:' + nm,
                                  'processors': 'minecraft:empty', 'projection': 'rigid'}, 'weight': 1}],
        'fallback': 'minecraft:empty'})
    st = {'type': 'minecraft:jigsaw', 'biomes': '#generatormods:has_structure/' + nm, 'max_distance_from_center': 128,
          'size': 1, 'spawn_overrides': {}, 'start_pool': 'generatormods:' + nm, 'use_expansion_hack': False,
          'project_start_to_heightmap': 'WORLD_SURFACE_WG', 'start_height': {'absolute': -s['embed']}}
    if s['under']:
        st.update(step='underground_structures', terrain_adaptation='encapsulate')
    else:
        st.update(step='surface_structures', terrain_adaptation='beard_thin')
    wjson('data/generatormods/worldgen/structure/%s.json' % nm, st)
wjson('data/generatormods/worldgen/structure_set/surface.json', {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400915, 'separation': 96, 'spacing': 256, 'spread_type': 'triangular'},
    'structures': [{'structure': 'generatormods:' + s['name'], 'weight': s['weight']} for s in gm_structs if not s['under']]})
wjson('data/generatormods/worldgen/structure_set/underground.json', {
    'placement': {'type': 'minecraft:random_spread', 'salt': 731400916, 'separation': 10, 'spacing': 32},
    'structures': [{'structure': 'generatormods:' + s['name'], 'weight': s['weight']} for s in gm_structs if s['under']]})
REPORT['gm_surface'] = [s['name'] for s in gm_structs if not s['under']]
REPORT['gm_underground'] = [s['name'] for s in gm_structs if s['under']]
# The walls, cities, streets and cellular-automaton ruins, rebuilt from Generatormods' own rules.
_P_KEEP = P
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gm_proc.py')).read())
P = _P_KEEP

# ------------------------------------------------------------------ Wild Caves
WCD = STAGE + '/wc_out/data/wildcaves'
C_TAGS = {
    '#c:is_overworld': ['#minecraft:is_overworld'], '#c:is_cave': ['minecraft:' + b for b in sorted(CAVES)],
    '#c:is_mountain': ['#minecraft:is_mountain'], '#c:is_ocean': ['#minecraft:is_ocean'],
    '#c:is_plains': ['minecraft:plains', 'minecraft:sunflower_plains', 'minecraft:snowy_plains', 'minecraft:meadow'],
    '#c:is_desert': ['minecraft:desert'],
    '#c:is_dry/overworld': ['minecraft:desert', '#minecraft:is_badlands', '#minecraft:is_savanna'],
    '#c:is_snowy': ['minecraft:' + b for b in sorted(TOK['SNOWY'])] + ['minecraft:frozen_river', 'minecraft:frozen_ocean', 'minecraft:deep_frozen_ocean'],
    '#c:is_swamp': ['minecraft:swamp', 'minecraft:mangrove_swamp'],
    '#c:is_tree/coniferous': ['#minecraft:is_taiga', 'minecraft:grove'],
    '#c:is_tree/deciduous': ['#minecraft:is_forest'], '#c:is_tree/jungle': ['#minecraft:is_jungle'],
    '#c:is_tree/savanna': ['#minecraft:is_savanna'],
    '#c:is_plateau': ['minecraft:savanna_plateau', 'minecraft:wooded_badlands', 'minecraft:meadow'],
    '#c:is_nether': ['#minecraft:is_nether'], '#c:is_end': ['#minecraft:is_end'],
}
for root, dirs, files in os.walk(WCD):
    for fn in files:
        src = os.path.join(root, fn)
        relp = os.path.relpath(src, WCD)
        if relp.startswith('structure/'):
            continue
        if relp.startswith('tags/worldgen/biome/'):
            d = json.load(open(src))
            vals = []
            for v in d['values']:
                v = v['id'] if isinstance(v, dict) else v
                vals += C_TAGS.get(v, [v] if not v.startswith('#c:') else [])
            wjson('data/wildcaves/' + relp, {'values': list(dict.fromkeys(vals))})
        elif relp.endswith('.json'):
            wjson('data/wildcaves/' + relp, json.load(open(src)))
        else:
            dst = os.path.join(OUT, 'data/wildcaves', relp)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy(src, dst)
# miner camp templates: rewrite in 26.3 format through the same block table
for root, dirs, files in os.walk(J + '/wc/x/data/wildcaves/structure'):
    for fn in files:
        src = os.path.join(root, fn)
        r = nbt.load(src)
        p = nbt.plain(nbt.COMPOUND, r)
        pal = [B.map_any(e['Name'], e.get('Properties', {})) for e in p['palette']]
        grid, bents = {}, {}
        for b in r['blocks'][1][1]:
            pos = tuple(b['pos'][1][1])
            st = pal[b['state'][1]]
            if st is None:
                grid[pos] = ['minecraft:air', {}]; continue
            if st[0] == 'minecraft:structure_void':
                continue
            grid[pos] = [st[0], dict(st[1])]
            if 'nbt' in b:
                tag = b['nbt'][1]
                if tag.get('id', (0, ''))[1] == 'minecraft:jigsaw':
                    keep = {k: v for k, v in tag.items() if k in ('id', 'joint', 'name', 'pool', 'target', 'final_state',
                                                                     'placement_priority', 'selection_priority')}
                    bents[pos] = keep
                else:
                    be = convert_be(tag, st[0])
                    if be:
                        bents[pos] = be
        write_template('data/wildcaves/structure/' + os.path.relpath(src, J + '/wc/x/data/wildcaves/structure'), p['size'], grid, bents)

# ------------------------------------------------------------------ Underground Biomes
UBT = J + '/ubc/x/assets/undergroundbiomes/textures/blocks'
IGNEOUS = ['redGranite', 'blackGranite', 'rhyolite', 'andesite', 'gabbro', 'basalt', 'komatiite', 'dacite']
METAMORPHIC = ['gneiss', 'eclogite', 'marble', 'quartzite', 'blueschist', 'greenschist', 'soapstone', 'migmatite']
SEDIMENTARY = ['limestone', 'chalk', 'shale', 'siltstone', 'ligniteBlock', 'dolomite', 'greywacke', 'chert']
CLASH = {'andesite': 'UB Andesite', 'basalt': 'UB Basalt'}
lang = {'itemGroup.%s.underground_biomes' % MODID: 'Underground Biomes'}
tab_items = []
stones_by_class = {'igneous': [], 'metamorphic': [], 'sedimentary': []}
pick, ore_repl, base_stone, craft_mat = [], [], [], []


def title(s):
    return CLASH.get(s, ' '.join(w.capitalize() for w in snake(s).split('_')))


def add_block(bid, tex, template, display, drop=None, silk=False, hardness=None):
    props = {}
    if hardness:
        props['hardness'] = hardness
        props['explosion_resistance'] = 6.0
    d = {'template': template, 'item': True}
    if props:
        d['properties'] = props
    wjson('data/%s/horizon/block/%s.json' % (MODID, bid), d)
    wjson('assets/%s/blockstates/%s.json' % (MODID, bid), {'variants': {'': {'model': '%s:block/%s' % (MODID, bid)}}})
    wjson('assets/%s/models/block/%s.json' % (MODID, bid), {'parent': 'minecraft:block/cube_all', 'textures': {'all': '%s:block/%s' % (MODID, bid)}})
    wjson('assets/%s/items/%s.json' % (MODID, bid), {'model': {'type': 'minecraft:model', 'model': '%s:block/%s' % (MODID, bid)}})
    dst = os.path.join(OUT, 'assets/%s/textures/block/%s.png' % (MODID, bid))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy(os.path.join(UBT, tex + '.png'), dst)
    me = '%s:%s' % (MODID, bid)
    if drop and drop != me:
        entries = [{'type': 'minecraft:alternatives', 'children': [
            {'type': 'minecraft:item', 'condition': 'minecraft:tool/can_silk_touch', 'name': me},
            {'type': 'minecraft:item', 'condition': {'type': 'minecraft:survives_explosion'}, 'name': drop}]}]
        pool = {'entries': entries, 'rolls': 1}
    else:
        pool = {'condition': {'type': 'minecraft:survives_explosion'}, 'entries': [{'type': 'minecraft:item', 'name': me}], 'rolls': 1}
    wjson('data/%s/loot_table/blocks/%s.json' % (MODID, bid), {'type': 'minecraft:block', 'pools': [pool], 'random_sequence': '%s:blocks/%s' % (MODID, bid)})
    lang['block.%s.%s' % (MODID, bid)] = display
    tab_items.append(me)
    pick.append(me)


for klass, names in (('igneous', IGNEOUS), ('metamorphic', METAMORPHIC), ('sedimentary', SEDIMENTARY)):
    for n in names:
        sid = snake(n).replace('_block', '')
        me = '%s:%s' % (MODID, sid)
        hard = {'igneous': 2.0, 'metamorphic': 1.8, 'sedimentary': 1.2}[klass]
        if klass == 'sedimentary':
            drop = 'minecraft:coal' if sid == 'lignite' else None
            add_block(sid, n, 'minecraft:stone', title(n.replace('Block', '')), drop=drop, hardness=hard)
        else:
            add_block(sid, n, 'minecraft:stone', title(n), drop='%s:%s_cobble' % (MODID, sid), hardness=hard)
            add_block(sid + '_cobble', n + 'Cobble', 'minecraft:cobblestone', title(n) + ' Cobblestone', hardness=hard + 0.5)
            add_block(sid + '_bricks', n + 'Brick', 'minecraft:stone_bricks', title(n) + ' Bricks', hardness=hard)
            wjson('data/%s/recipe/%s_from_cobble.json' % (MODID, sid), {
                'type': 'minecraft:smelting', 'category': 'blocks', 'cookingtime': 200, 'experience': 0.1,
                'ingredient': '%s:%s_cobble' % (MODID, sid), 'result': {'id': me}})
            wjson('data/%s/recipe/%s_bricks.json' % (MODID, sid), {
                'type': 'minecraft:crafting_shaped', 'category': 'building', 'key': {'#': me}, 'pattern': ['##', '##'],
                'result': {'count': 4, 'id': '%s:%s_bricks' % (MODID, sid)}})
            craft_mat.append('%s:%s_cobble' % (MODID, sid))
        stones_by_class[klass].append(sid)
        ore_repl.append(me)
        base_stone.append(me)
    if klass == 'sedimentary':
        pass

wjson('data/%s/horizon/creative_tab/underground_biomes.json' % MODID, {'title': 'itemGroup.%s.underground_biomes' % MODID,
                                                                       'icon': '%s:red_granite' % MODID, 'items': tab_items})
wjson('assets/%s/lang/en_us.json' % MODID, lang)
wjson('data/minecraft/tags/block/mineable/pickaxe.json', {'values': pick})
wjson('data/minecraft/tags/block/stone_ore_replaceables.json', {'values': ore_repl})
wjson('data/minecraft/tags/block/base_stone_overworld.json', {'values': base_stone})
wjson('data/minecraft/tags/item/stone_crafting_materials.json', {'values': craft_mat})
wjson('data/minecraft/tags/item/stone_tool_materials.json', {'values': craft_mat})

BANDS = {  # class -> list of (target block, min y, max y)
    'sedimentary': [('minecraft:stone', 30, 160)],
    'metamorphic': [('minecraft:stone', -8, 80)],
    'igneous': [('minecraft:stone', -8, 40), ('minecraft:deepslate', -60, 4)],
}
STRATA_CHANCE = 64      # elsewhere: each stone in about 1 chunk of 64, so most of the world stays stone
STONY_CHANCE = 1        # stone biomes: every stone in every chunk, STONY_COUNT big blobs each, 2 to 48 below the surface
STONY_COUNT = 2
# Stone biomes: the mountains and stony places, vanilla's and Biomes O' Plenty's (unknown ids are dropped).
STONY = ['minecraft:stony_peaks', 'minecraft:jagged_peaks', 'minecraft:frozen_peaks', 'minecraft:stony_shore',
         'minecraft:windswept_hills', 'minecraft:windswept_gravelly_hills', 'minecraft:windswept_forest',
         'minecraft:dripstone_caves', 'minecraft:snowy_slopes', 'minecraft:grove',
         'biomesoplenty:crag', 'biomesoplenty:jade_cliffs', 'biomesoplenty:rocky_rainforest',
         'biomesoplenty:rocky_shrubland', 'biomesoplenty:volcanic_plains', 'biomesoplenty:volcano',
         'biomesoplenty:highland', 'biomesoplenty:highland_moor', 'biomesoplenty:wintry_origin_valley',
         'biomesoplenty:dryland', 'biomesoplenty:lush_desert']
wjson('data/%s/tags/worldgen/biome/stony.json' % MODID, {'values': STONY})
feats, stony_feats = [], []
for klass, sids in stones_by_class.items():
    for sid in sids:
        for target, lo, hi in BANDS[klass]:
            fid = '%s_%s' % (sid, target.split(':')[1])
            # Big blobs: radius 8 to 12 (the most a replace-blobs feature takes), about 20 blocks across.
            wjson('data/%s/worldgen/feature/strata/%s.json' % (MODID, fid), {
                'type': 'minecraft:netherrack_replace_blobs',
                'radius': {'type': 'minecraft:uniform', 'min_inclusive': 8, 'max_inclusive': 12},
                'state': '%s:%s' % (MODID, sid), 'target': target})
            wjson('data/%s/worldgen/placed_feature/strata/%s.json' % (MODID, fid), {
                'feature': '%s:strata/%s' % (MODID, fid),
                'placement': [{'type': 'minecraft:rarity_filter', 'chance': STRATA_CHANCE},
                              {'type': 'minecraft:in_square'},
                              {'type': 'minecraft:height_range', 'height': {'type': 'minecraft:uniform',
                                                                            'min_inclusive': {'absolute': lo}, 'max_inclusive': {'absolute': hi}}},
                              {'type': 'minecraft:biome'}]})
            feats.append('%s:strata/%s' % (MODID, fid))
            if target != 'minecraft:stone':
                continue
            # Stone biomes: from the surface down into the mountain (2 to 48 blocks), where the
            # biome is still the stone biome's (deeper down it is often a cave biome).
            wjson('data/%s/worldgen/placed_feature/stony/%s.json' % (MODID, fid), {
                'feature': '%s:strata/%s' % (MODID, fid),
                'placement': [{'type': 'minecraft:count', 'count': STONY_COUNT},
                              {'type': 'minecraft:in_square'},
                              {'type': 'minecraft:heightmap', 'heightmap': 'OCEAN_FLOOR_WG'},
                              # Horizon's offset takes -16..16 a step, so three steps make 2 to 48 down.
                              ] + [{'type': 'minecraft:offset', 'x': 0, 'z': 0,
                                    'y': {'type': 'minecraft:uniform', 'min_inclusive': -16, 'max_inclusive': lo}}
                                   for lo in (-2, 0, 0)] + [
                              {'type': 'minecraft:biome'}]})
            stony_feats.append('%s:stony/%s' % (MODID, fid))
# The rare strata go everywhere; the stone biomes also get the dense ones, reaching up into the peaks.
wjson('data/%s/neoforge/biome_modifier/strata.json' % MODID, {
    'type': 'neoforge:add_features', 'biomes': '#minecraft:is_overworld', 'features': feats, 'step': 'underground_ores'})
wjson('data/%s/neoforge/biome_modifier/strata_stony.json' % MODID, {
    'type': 'neoforge:add_features', 'biomes': '#%s:stony' % MODID, 'features': stony_feats, 'step': 'underground_ores'})
REPORT['ubc_blocks'] = len(tab_items)
REPORT['ubc_strata_features'] = len(feats)

# ------------------------------------------------------------------ manifest
with open(OUT + '/horizon-mod.toml', 'w', newline='\n') as f:
    f.write('''id = "%s"
name = "Structure Add-on"
version = "0.3.0"
description = "Horizon port of Underground Biomes Constructs (big stone strata, rare except in stone biomes), Recurrent Complex, Ancient Structures and Generatormods (very rare surface structures, walls, cities and ruins; underground cities and dungeons) and Wild Caves (cave decoration, miner camps). Data only."
authors = ["Exterminator Jeff & Zeno410 (Underground Biomes)", "Ivorius (Recurrent Complex)", "DevDyna (Wild Caves)", "TheGoldenWorld (Ancient Structures)", "formivore and template authors (Generatormods)", "mxpbxb (Horizon port)"]
api = "0.2"
side = "both"
capabilities = ["registries"]
namespaces = ["reccomplex", "ancientstructures", "wildcaves", "generatormods"]
''' % MODID)

REPORT['block_stats'] = {k: dict(collections.Counter(v).most_common(40)) for k, v in B.STATS.items()}
with open(P + '/report.json', 'w') as f:
    json.dump(REPORT, f, indent=1, default=lambda o: dict(o))
print(json.dumps({k: (v if not isinstance(v, (list, dict)) or len(str(v)) < 1500 else str(v)[:1500]) for k, v in REPORT.items()}, indent=1, default=lambda o: dict(o)))
