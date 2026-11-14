"""Vanilla 26.3 block state table, legacy (1.7.10/1.12) flattening, Dawn of Time block remapping,
and the connection pass for fences/walls/panes."""
import json, os, glob, re

# The game's block facts, from its mod-content cache (HORIZON_CACHE, or any Windows user's cache under WSL).
_CACHE = os.environ.get('HORIZON_CACHE') or '/mnt/c/Users/*/AppData/Roaming/horizon/.horizon-cache'
FACTS = sorted(glob.glob(os.path.join(_CACHE, 'mod-content', '*', 'facts.json')), key=os.path.getsize)[0]
FLAT = os.path.expanduser('~/horizon-dev/forks/horizon/crates/horizon-world/src/datafix/block_state_data.txt')

VB = {}  # name -> {prop: set(values)}
VDEF = {}


def _load_facts():
    d = json.load(open(FACTS))
    st = d['states']
    for s in st:
        desc = s[4]
        name = desc['id']
        if not name.startswith('minecraft:'):
            continue
        props = VB.setdefault(name, {})
        for k, v in (desc.get('properties') or {}).items():
            props.setdefault(k, set()).add(v)
    for name, idx in d['defaults'].items():
        if name.startswith('minecraft:'):
            VDEF[name] = dict(st[idx][4].get('properties') or {})


_load_facts()

RENAMES = {
    'minecraft:grass': 'minecraft:short_grass', 'minecraft:sign': 'minecraft:oak_sign',
    'minecraft:wall_sign': 'minecraft:oak_wall_sign', 'minecraft:chain': 'minecraft:iron_chain',
    'minecraft:mob_spawner': 'minecraft:spawner', 'minecraft:melon_block': 'minecraft:melon','minecraft:oak_bark': 'minecraft:oak_wood', 'minecraft:spruce_bark': 'minecraft:spruce_wood',
    'minecraft:birch_bark': 'minecraft:birch_wood', 'minecraft:jungle_bark': 'minecraft:jungle_wood', 'minecraft:acacia_bark': 'minecraft:acacia_wood',
    'minecraft:dark_oak_bark': 'minecraft:dark_oak_wood',
}

STATS = {}


def fix(name, props=None):
    """Return (name, props) valid in 26.3, or None when the block does not exist."""
    props = dict(props or {})
    if name not in VB and name in RENAMES:
        name = RENAMES[name]
    if name not in VB:
        STATS.setdefault('missing', {}).setdefault(name, 0)
        STATS['missing'][name] += 1
        return None
    vp = VB[name]
    # walls changed from booleans to none/low/tall in 1.16
    if name.endswith('_wall') and 'up' in vp:
        for side in ('north', 'south', 'east', 'west'):
            if props.get(side) == 'true': props[side] = 'low'
            elif props.get(side) == 'false': props[side] = 'none'
    out = {}
    for k, v in props.items():
        v = str(v)
        if k in vp and v in vp[k]:
            out[k] = v
    return name, out


# ---------------- legacy 1.12 flattening ----------------
LEG_ID = {}     # legacy name -> block id
FLAT_MAP = {}   # numeric id<<4|meta -> (name, props)


def _load_flat():
    for line in open(FLAT):
        if line.startswith('#') or not line.strip():
            continue
        f = line.rstrip('\n').split('\t')
        i = int(f[0])
        props = dict(p.split('=', 1) for p in f[2].split(';') if p) if len(f) > 2 else {}
        FLAT_MAP[i] = (f[1], props)
        for j in range(3, len(f) - 1, 2):
            LEG_ID.setdefault(f[j], i >> 4)


_load_flat()

# 1.13 -> 1.14+ renames not covered by the flattening table
POST13 = {'minecraft:stone_slab': 'minecraft:smooth_stone_slab', 'minecraft:sign': 'minecraft:oak_sign',
          'minecraft:wall_sign': 'minecraft:oak_wall_sign'}


def legacy(name, meta):
    bid = LEG_ID.get(name)
    if bid is None:
        return None
    s = FLAT_MAP.get(bid << 4 | (meta & 15))
    if s is None:
        s = next((FLAT_MAP[bid << 4 | m] for m in range(16) if (bid << 4 | m) in FLAT_MAP), None)
    if s is None or s[0] == '%%FILTER_ME%%':
        return None
    n, p = s
    n = POST13.get(n, n)
    return fix(n, p)


# ---------------- Dawn of Time Builder -> vanilla ----------------
WOODS = [('waxed_oak', 'oak'), ('charred_spruce', 'dark_oak'), ('spruce', 'spruce'), ('birch', 'birch'),
         ('jungle', 'jungle'), ('oak', 'oak'), ('acacia', 'acacia'), ('dark_oak', 'dark_oak')]
# stone-ish families: (dotb prefix, full block, stairs, slab, wall)
STONES = [
    ('stone_bricks_masonry', 'stone_bricks', 'stone_brick_stairs', 'stone_brick_slab', 'stone_brick_wall'),
    ('stone_bricks', 'stone_bricks', 'stone_brick_stairs', 'stone_brick_slab', 'stone_brick_wall'),
    ('limestone_bricks', 'sandstone', 'sandstone_stairs', 'sandstone_slab', 'sandstone_wall'),
    ('cobbled_limestone', 'sandstone', 'sandstone_stairs', 'sandstone_slab', 'sandstone_wall'),
    ('limestone', 'smooth_sandstone', 'smooth_sandstone_stairs', 'smooth_sandstone_slab', 'sandstone_wall'),
    ('marble', 'quartz_block', 'quartz_stairs', 'quartz_slab', 'diorite_wall'),
    ('cut_sandstone', 'cut_sandstone', 'sandstone_stairs', 'cut_sandstone_slab', 'sandstone_wall'),
    ('smooth_sandstone', 'smooth_sandstone', 'smooth_sandstone_stairs', 'smooth_sandstone_slab', 'sandstone_wall'),
    ('sandstone', 'sandstone', 'sandstone_stairs', 'sandstone_slab', 'sandstone_wall'),
    ('flat_roof_tiles', 'bricks', 'brick_stairs', 'brick_slab', 'brick_wall'),
    ('gray_roof_tiles', 'deepslate_tiles', 'deepslate_tile_stairs', 'deepslate_tile_slab', 'deepslate_tile_wall'),
    ('ochre_roof_tiles', 'red_sandstone', 'red_sandstone_stairs', 'red_sandstone_slab', 'red_sandstone_wall'),
    ('roofing_slates', 'polished_blackstone_bricks', 'polished_blackstone_brick_stairs', 'polished_blackstone_brick_slab', 'polished_blackstone_brick_wall'),
    ('thatch_wheat', 'hay_block', 'bamboo_mosaic_stairs', 'bamboo_mosaic_slab', 'bamboo_fence'),
    ('stepping_stones', 'cobblestone', 'cobblestone_stairs', 'cobblestone_slab', 'cobblestone_wall'),
    ('terracotta', 'terracotta', 'mud_brick_stairs', 'mud_brick_slab', 'mud_brick_wall'),
]
PLASTER_COLORS = {'red': 'red_terracotta', 'blue': 'light_blue_terracotta', 'green': 'green_terracotta',
                  'yellow': 'yellow_terracotta', 'white': 'white_terracotta', 'black': 'black_terracotta'}

FENCEY = ('fancy_fence', 'fancy_railing', 'railing', 'baluster', 'lattice', 'pergola', 'support_beam', 'roof_support',
          'support_slab', 'beam', 'fence')


def _shape(rest, full, stairs, slab, wall, props, fence=None):
    """Map a DoTB shape suffix to a vanilla block of a family."""
    if rest.endswith('_fence_gate') and fence:
        return fence + '_gate', props
    if rest.endswith('_stairs') or rest.endswith('_edge'):
        return stairs, props
    if rest.endswith('_slab') or rest.endswith('_plate'):
        p = {'type': 'top' if props.get('half') == 'top' or props.get('type') == 'top' else 'bottom'}
        if props.get('type') == 'double': p['type'] = 'double'
        return slab, p
    if rest.endswith('_wall') and not rest.startswith('paper'):
        return wall, {}
    for s in FENCEY:
        if rest.endswith(s):
            return (fence or wall), {}
    return full, {}


DECOR = {
    'paper_lamp': ('lantern', {}), 'red_paper_lantern': ('lantern', {'hanging': 'true'}),
    'iron_fancy_lantern': ('lantern', {}), 'stone_lantern': ('lantern', {}),
    'candlestick': ('candle', {'candles': '1'}), 'waxed_oak_chandelier': ('lantern', {'hanging': 'true'}),
    'plastered_stone_cresset': ('lantern', {}), 'fireplace': ('campfire', {'lit': 'false'}),
    'irori_fireplace': ('campfire', {'lit': 'false'}), 'limestone_fireplace': ('campfire', {'lit': 'false'}),
    'stone_bricks_fireplace': ('campfire', {'lit': 'false'}),
    'paper_door': ('birch_door', None), 'paper_wall': ('white_wool', {}), 'paper_wall_flowery': ('pink_wool', {}),
    'paper_wall_window': ('white_stained_glass', {}), 'paper_folding_screen': ('white_wool', {}),
    'tatami_mat': ('yellow_carpet', {}), 'small_tatami_mat': ('yellow_carpet', {}),
    'tatami_floor': ('bamboo_mosaic', {}), 'small_tatami_floor': ('bamboo_mosaic', {}),
    'light_gray_futon': ('light_gray_carpet', {}), 'persian_carpet_red': ('red_carpet', {}),
    'persian_carpet_delicate_red': ('red_carpet', {}), 'rammed_dirt': ('packed_mud', {}),
    'waxed_oak_framed_rammed_dirt': ('mud_bricks', {}), 'waxed_oak_framed_rammed_dirt_pillar': ('mud_bricks', {}),
    'mosaic_floor': ('polished_granite', {}), 'mosaic_floor_delicate': ('polished_granite', {}),
    'mosaic_floor_rosette': ('polished_granite', {}), 'curved_raked_gravel': ('gravel', {}),
    'straight_raked_gravel': ('gravel', {}), 'marble_statue_mars': ('quartz_pillar', {}),
    'feathered_serpent_sculpture': ('chiseled_sandstone', {}), 'serpent_sculpted_column': ('chiseled_sandstone', {}),
    'marble_coffer': ('chiseled_quartz_block', {}), 'roman_fresco_black': ('black_terracotta', {}),
    'roman_fresco_red': ('red_terracotta', {}), 'wild_maize': ('tall_grass', None),
    'white_little_flag': ('air', {}), 'sake_bottle': ('air', {}), 'sake_cup': ('air', {}),
    'lattice_waxed_oak_window': ('oak_trapdoor', None), 'stone_bricks_arrowslit': ('stone_bricks', {}),
    'stone_bricks_chimney': ('stone_bricks', {}), 'limestone_chimney': ('sandstone', {}),
    'stone_bricks_faucet': ('stone_bricks', {}), 'stone_bricks_water_jet': ('stone_bricks', {}),
    'stone_bricks_pool': ('stone_brick_slab', {'type': 'bottom'}), 'stone_bricks_small_pool': ('stone_brick_slab', {'type': 'bottom'}),
    'charred_spruce_foundation': ('dark_oak_planks', {}), 'charred_spruce_boards': ('dark_oak_planks', {}),
    'terracotta_wall': ('terracotta', {}),
}


def dotb(local, props):
    """Return (vanilla name without namespace, props) for a dawnoftimebuilder block."""
    if local in DECOR:
        n, p = DECOR[local]
        return n, (dict(props) if p is None else dict(props, **p) if p else {})
    if 'teacup' in local or 'teapot' in local:
        return 'air', {}
    if 'flower_pot' in local or local.startswith('planter_'):
        return 'flower_pot', {}
    # wood families
    for pre, wood in WOODS:
        if local.startswith(pre + '_'):
            rest = local[len(pre) + 1:]
            if rest in ('planks', 'boards', 'foundation'): return wood + '_planks', {}
            if rest == 'log_stripped': return 'stripped_%s_log' % wood, props
            if rest == 'door': return wood + '_door', props
            if rest in ('trapdoor', 'shutters', 'small_shutters'): return wood + '_trapdoor', dict(props, open=props.get('open', 'true') if 'shutters' in rest else props.get('open', 'false'))
            if rest == 'fence_gate': return wood + '_fence_gate', props
            if rest.startswith('timber_frame'): return 'white_terracotta', {}
            if rest in ('chair', 'couch', 'legless_chair', 'footstool'): return wood + '_stairs', {'facing': props.get('facing', 'north')}
            if rest in ('table',): return wood + '_fence', {}
            if rest in ('low_table',): return wood + '_slab', {'type': 'bottom'}
            if rest in ('leaves_edge', 'leaves_plate'): return wood + '_leaves', {'persistent': 'true'}
            if rest.startswith('planks_'):
                return _shape(rest, wood + '_planks', wood + '_stairs', wood + '_slab', wood + '_fence', props, wood + '_fence')
            if rest == 'wall': return wood + '_planks', {}
            return _shape(rest, wood + '_planks', wood + '_stairs', wood + '_slab', wood + '_fence', props, wood + '_fence')
    # plastered / painted stone
    m = re.match(r'(?:(red|blue|green|yellow|white|black)_)?(?:\w+_)?(plastered_stone|painted_stone)(.*)', local)
    if m:
        color, kind, rest = m.groups()
        full = PLASTER_COLORS.get(color, 'calcite' if kind == 'plastered_stone' else 'white_terracotta')
        if rest.endswith('_window'): return 'glass', {}
        if rest.endswith('_column'): return full, {}
        return _shape(rest or '_block', full, 'mud_brick_stairs' if full != 'calcite' else 'smooth_quartz_stairs',
                      'mud_brick_slab' if full != 'calcite' else 'smooth_quartz_slab', 'mud_brick_wall' if full != 'calcite' else 'diorite_wall', props)
    for pre, full, stairs, slab, wall in STONES:
        if local == pre or local.startswith(pre + '_'):
            rest = local[len(pre):]
            if pre == 'marble' and ('column' in rest): return 'quartz_pillar', {}
            if 'column' in rest: return 'cut_sandstone' if 'sandstone' in pre else full, {}
            return _shape(rest or '_block', full, stairs, slab, wall, props)
    if local.startswith('cut_sandstone_bot_ochre_roof_tiles'):
        return 'red_sandstone_slab', {'type': 'bottom'}
    if 'chiseled' in local or 'ornamented' in local or 'frieze' in local or 'sculpted' in local:
        for c in PLASTER_COLORS:
            if local.startswith(c): return PLASTER_COLORS[c], {}
        return 'chiseled_quartz_block', {}
    return None


def map_any(name, props):
    """Any block name from AS/WC NBT -> valid 26.3 (name, props) or None for air."""
    if name.startswith('dawnoftimebuilder:'):
        r = dotb(name.split(':', 1)[1], props)
        if r is None:
            STATS.setdefault('dotb_unmapped', {}).setdefault(name, 0); STATS['dotb_unmapped'][name] += 1
            return None
        n, p = r
        if n == 'air':
            return None
        out = fix('minecraft:' + n, p)
        if out is None:
            STATS.setdefault('dotb_bad', {}).setdefault(name + '->' + n, 0); STATS['dotb_bad'][name + '->' + n] += 1
        return out
    if not name.startswith('minecraft:'):
        STATS.setdefault('foreign', {}).setdefault(name, 0); STATS['foreign'][name] += 1
        return None
    if name in ('minecraft:command_block', 'minecraft:chain_command_block', 'minecraft:repeating_command_block'):
        return None
    return fix(name, props)


# ---------------- connections ----------------
NONFULL = re.compile(r'(slab|stairs|fence|door|trapdoor|torch|lantern|flower|pane|carpet|sign|button|plate|rail|'
                     r'ladder|vine|grass|fern|bush|sapling|wall|bars|candle|campfire|chain|pot|banner|head|skull|'
                     r'leaves|glass$|snow$|lever|wire|repeater|comparator|bed|cake|cactus|cane|mushroom$|cobweb|'
                     r'air|water|lava|fire|structure_void|chest|anvil|cauldron|brewing|hopper|lily|dead|crop|wheat|'
                     r'carrots|potatoes|beetroots|farmland|path|dripleaf|azalea|lichen|moss_carpet|tripwire|end_rod|lightning|scaffold)')


def conn_kind(name):
    if name is None: return None
    n = name.split(':')[1]
    if n.endswith('_fence') : return 'fence_nether' if n == 'nether_brick_fence' else 'fence'
    if n.endswith('_wall') and 'up' in VB.get(name, {}): return 'wall'
    if n.endswith('glass_pane') or n == 'iron_bars': return 'pane'
    return None


def is_full(name):
    if name is None: return False
    return not NONFULL.search(name.split(':')[1])


def connect(grid):
    """grid: dict (x,y,z) -> [name, props]. Recompute side connections in place."""
    dirs = {'north': (0, 0, -1), 'south': (0, 0, 1), 'east': (1, 0, 0), 'west': (-1, 0, 0)}
    for pos, st in grid.items():
        k = conn_kind(st[0])
        if not k:
            continue
        x, y, z = pos
        for side, (dx, dy, dz) in dirs.items():
            nb = grid.get((x + dx, y, z + dz))
            nn = nb[0] if nb else None
            nk = conn_kind(nn)
            c = False
            if nk == k or (k.startswith('fence') and nk and nk.startswith('fence') and k == nk):
                c = True
            elif is_full(nn):
                c = True
            elif k.startswith('fence') and nn and nn.endswith('_fence_gate'):
                c = True
            elif k == 'wall' and nn and (nn.endswith('_fence_gate') or nk == 'pane'):
                c = True
            elif k == 'pane' and nk == 'wall':
                c = True
            if k == 'wall':
                st[1][side] = 'low' if c else 'none'
            else:
                st[1][side] = 'true' if c else 'false'
        if k == 'wall':
            st[1]['up'] = 'true'
