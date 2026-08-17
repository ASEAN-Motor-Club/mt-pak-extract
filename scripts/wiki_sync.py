#!/usr/bin/env python3
"""
Wiki Sync — Generate DokuWiki pages from Motor Town ETL database.

Combines system-generated game data sections with user-contributed wiki content.
System sections are identified structurally by DokuWiki headings (e.g.
===== Specifications =====). User content between the page heading and the
specs section is preserved across updates. Any legacy <!-- SYSTEM:... -->
markers are automatically stripped.

Usage:
    python3 scripts/wiki_sync.py --db motortown.db --wiki-dir /path/to/pages --dry-run
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A section of a wiki page."""
    name: str  # e.g. "infobox", "specs", "axles", "i18n", "user:0", "user:1"
    content: str
    is_system: bool = False

    @property
    def is_user(self) -> bool:
        return not self.is_system


@dataclass
class Part:
    """A vehicle part from the DB."""
    id: str
    name: str
    part_type: str
    cost: int
    mass_kg: float
    is_hidden: bool
    # Localization: the raw `name` column value (a locres key GUID, or a short
    # key like 'Stock'/'Stage1'/`X_Name`, or None for parts with no locres entry).
    locres_key: Optional[str] = None
    # Vehicle-side install restrictions (part fits these vehicles).
    vehicle_types: list = field(default_factory=list)   # stripped enum values
    truck_classes: list = field(default_factory=list)
    truck_class_include_none: bool = False
    vehicle_keys: list = field(default_factory=list)
    override_vehicle_keys: list = field(default_factory=list)
    slots: list = field(default_factory=list)
    # tuning stats: {struct_type: {field: value}}
    stats: dict = field(default_factory=dict)


@dataclass
class Vehicle:
    """Vehicle data from DB."""
    id: str
    name: str
    vehicle_type: str
    truck_class: str
    cost: int
    comport: int
    is_hidden: bool
    is_disabled: bool
    air_drag: float = 0.0
    chassis_mass_kg: float = 0.0
    total_weight_kg: float = 0.0
    parts_mass_kg: float = 0.0
    default_parts: list = field(default_factory=list)  # [(slot, part_id)]
    # Cargo space
    cargo_space_type: str = ''
    cargo_length_m: float = 0.0
    cargo_width_m: float = 0.0
    cargo_height_m: float = 0.0
    cargo_volume_m3: float = 0.0
    cargo_dump_volume_kl: float = 0.0
    cargo_fix: bool = False
    cargo_unlimited_height: bool = False
    # Capabilities
    is_taxiable: bool = False
    is_limoable: bool = False
    is_busable: bool = False
    is_race_car: bool = False
    can_haul_trailer: bool = False
    has_fuel_pump: bool = False
    # Delivery
    delivery_payment_multiplier: float = 1.0
    delivery_base_payment: int = 0
    # Engine info (parsed from part name)
    engine_hp: int = 0
    engine_id: str = ''
    # Fuel tank
    fuel_capacity_liters: float = 0.0
    # Final drive ratio
    final_drive_ratio: float = 0.0
    # Tags
    tags: list = field(default_factory=list)


@dataclass
class Cargo:
    """Cargo data from DB."""
    id: str
    name: str
    cargo_type: str
    volume_size: int
    weight_kg: float = 0.0
    payment_per_km: int = 0
    payment_multiplier: float = 1.0
    base_payment: int = 0
    min_delivery_distance: int = 0
    max_delivery_distance: int = 0
    allow_stacking: bool = False
    fragile: int = 0
    is_deprecated: bool = False
    space_types: list = field(default_factory=list)
    produced_at: list = field(default_factory=list)  # [(location, inputs, time)]
    consumed_at: list = field(default_factory=list)  # [(location, outputs, time)]


# ---------------------------------------------------------------------------
# Page Parser
# ---------------------------------------------------------------------------
SYSTEM_MARKER_RE = re.compile(r'^\s*<!-- /?SYSTEM:\w+ -->\s*$')

# Pattern for structural section detection
INFOBOX_START_RE = re.compile(r'^{{infobox>')
INFOBOX_END_RE = re.compile(r'^}}')
HEADING_RE = re.compile(r'^====== .+ ======')
SPECS_SECTION_RE = re.compile(r'^={3,5} Specifications ={3,5}')
AXLE_SECTION_RE = re.compile(r'^={3,5} Axle [Ii]nfo ={3,5}')
I18N_SECTION_RE = re.compile(r'^={3,5} In [Oo]ther [Ll]anguages ={3,5}')


def _strip_markers(text: str) -> str:
    """Remove any legacy <!-- SYSTEM:... --> markers from page text."""
    lines = text.split('\n')
    return '\n'.join(line for line in lines if not SYSTEM_MARKER_RE.match(line))


def parse_page(text: str) -> list[Section]:
    """Parse a vehicle page into sections using structural detection.
    
    Handles both pages with and without legacy markers (markers are stripped first).
    """
    text = _strip_markers(text)
    sections = []
    lines = text.split('\n')
    i = 0

    # --- Infobox ---
    if i < len(lines) and INFOBOX_START_RE.match(lines[i]):
        infobox_lines = []
        while i < len(lines):
            infobox_lines.append(lines[i])
            if INFOBOX_END_RE.match(lines[i].strip()):
                i += 1
                break
            i += 1
        sections.append(Section("infobox", '\n'.join(infobox_lines), is_system=True))

    # Skip blank lines
    while i < len(lines) and not lines[i].strip():
        i += 1

    # --- Heading (====== Name ======) ---
    heading_lines = []
    if i < len(lines) and HEADING_RE.match(lines[i]):
        heading_lines.append(lines[i])
        i += 1
        # Include the one-liner description: **Name** is a ...
        if i < len(lines) and lines[i].startswith('**'):
            heading_lines.append(lines[i])
            i += 1
        sections.append(Section("heading", '\n'.join(heading_lines), is_system=True))

    # --- User content (between heading and specs/axle/i18n) ---
    user_lines = []
    while i < len(lines):
        if SPECS_SECTION_RE.match(lines[i]):
            break
        if AXLE_SECTION_RE.match(lines[i]):
            break
        if I18N_SECTION_RE.match(lines[i]):
            break
        user_lines.append(lines[i])
        i += 1

    user_content = '\n'.join(user_lines).strip()
    if user_content:
        sections.append(Section("user:body", user_content, is_system=False))

    # --- Skip system-generated sections (Specs, Cargo Space, Capabilities,
    #     Delivery, Default Parts) — everything until Axle/i18n ---
    while i < len(lines):
        if AXLE_SECTION_RE.match(lines[i]):
            break
        if I18N_SECTION_RE.match(lines[i]):
            break
        i += 1

    # --- Axle section ---
    if i < len(lines) and AXLE_SECTION_RE.match(lines[i]):
        axle_lines = []
        axle_lines.append(lines[i])
        i += 1
        while i < len(lines) and not I18N_SECTION_RE.match(lines[i]):
            axle_lines.append(lines[i])
            i += 1
        content = '\n'.join(axle_lines).rstrip()
        sections.append(Section("axles", content, is_system=True))

    # --- i18n section ---
    if i < len(lines) and I18N_SECTION_RE.match(lines[i]):
        i18n_lines = []
        while i < len(lines):
            i18n_lines.append(lines[i])
            i += 1
        content = '\n'.join(i18n_lines).rstrip()
        sections.append(Section("i18n", content, is_system=True))

    return sections


def extract_infobox_image(infobox_content: str) -> Optional[str]:
    """Extract the image = ... line from an infobox, if present."""
    for line in infobox_content.split('\n'):
        if line.strip().startswith('image'):
            return line
    return None


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def _parse_hp_from_id(engine_id: str) -> int:
    """Extract horsepower from engine part ID like 'SmallBlock_140HP' -> 140."""
    m = re.search(r'(\d+)HP', engine_id)
    return int(m.group(1)) if m else 0


def load_vehicles(conn: sqlite3.Connection) -> list[Vehicle]:
    """Load all vehicles from DB."""
    cursor = conn.cursor()
    inner = conn.cursor()  # Separate cursor for sub-queries
    vehicles = []

    for row in cursor.execute("""
        SELECT v.id, v.name, v.vehicle_type, v.truck_class, v.cost, v.comport,
               v.is_hidden, v.is_disabled,
               COALESCE(vw.chassis_mass_kg, 0) as chassis_mass_kg,
               v.is_taxiable, v.is_limoable, v.is_busable, v.is_race_car,
               v.can_haul_trailer, v.has_fuel_pump,
               v.delivery_payment_multiplier, v.delivery_base_payment
        FROM vehicles v
        LEFT JOIN vehicle_weights vw ON v.id = vw.vehicle_id
        WHERE v.is_hidden = 0 OR v.is_hidden IS NULL
        ORDER BY v.vehicle_type, v.name
    """):
        v = Vehicle(
            id=row[0], name=row[1] or row[0], vehicle_type=row[2] or '',
            truck_class=row[3] or '', cost=row[4] or 0, comport=row[5] or 0,
            is_hidden=bool(row[6]), is_disabled=bool(row[7]),
            chassis_mass_kg=row[8] or 0.0,
            is_taxiable=bool(row[9]), is_limoable=bool(row[10]),
            is_busable=bool(row[11]), is_race_car=bool(row[12]),
            can_haul_trailer=bool(row[13]), has_fuel_pump=bool(row[14]),
            delivery_payment_multiplier=row[15] or 1.0,
            delivery_base_payment=row[16] or 0,
        )

        # Load default parts
        for part_row in inner.execute("""
            SELECT dp.slot, dp.part_id
            FROM vehicle_default_parts dp
            WHERE dp.vehicle_id = ?
            ORDER BY dp.slot
        """, (v.id,)):
            v.default_parts.append((part_row[0], part_row[1]))

        # Calculate total weight from parts
        parts_mass = inner.execute("""
            SELECT COALESCE(SUM(vp.mass_kg), 0)
            FROM vehicle_default_parts dp
            JOIN vehicle_parts vp ON dp.part_id = vp.id
            WHERE dp.vehicle_id = ?
        """, (v.id,)).fetchone()[0] or 0.0

        v.parts_mass_kg = parts_mass
        v.total_weight_kg = v.chassis_mass_kg + parts_mass

        # Get air drag from the first aero part or body
        drag_row = inner.execute("""
            SELECT vp.air_drag_multiplier
            FROM vehicle_default_parts dp
            JOIN vehicle_parts vp ON dp.part_id = vp.id
            WHERE dp.vehicle_id = ? AND vp.air_drag_multiplier IS NOT NULL
            AND vp.air_drag_multiplier != 0
            LIMIT 1
        """, (v.id,)).fetchone()
        if drag_row:
            v.air_drag = drag_row[0] or 0.0

        # Engine info
        engine_id = next((pid for slot, pid in v.default_parts if slot == 'Engine'), None)
        if engine_id:
            v.engine_id = engine_id
            v.engine_hp = _parse_hp_from_id(engine_id)

        # Final drive ratio
        fdr_id = next((pid for slot, pid in v.default_parts if slot == 'FinalDriveRatio'), None)
        if fdr_id:
            fdr_row = inner.execute(
                "SELECT final_drive_ratio FROM vehicle_parts WHERE id = ?", (fdr_id,)
            ).fetchone()
            if fdr_row and fdr_row[0]:
                v.final_drive_ratio = fdr_row[0]

        # Cargo space (from view)
        cargo_row = inner.execute("""
            SELECT cargo_space_type, length_m, width_m, height_m,
                   volume_m3, dump_volume_kl, fix_cargo, unlimited_height
            FROM vehicles_with_cargo_space WHERE id = ?
        """, (v.id,)).fetchone()
        if cargo_row:
            v.cargo_space_type = cargo_row[0] or ''
            v.cargo_length_m = cargo_row[1] or 0.0
            v.cargo_width_m = cargo_row[2] or 0.0
            v.cargo_height_m = cargo_row[3] or 0.0
            v.cargo_volume_m3 = cargo_row[4] or 0.0
            v.cargo_dump_volume_kl = cargo_row[5] or 0.0
            v.cargo_fix = bool(cargo_row[6])
            v.cargo_unlimited_height = bool(cargo_row[7])

        # Tags
        for tag_row in inner.execute(
            "SELECT DISTINCT tag FROM vehicle_tags WHERE vehicle_id = ?", (v.id,)
        ):
            v.tags.append(tag_row[0])

        vehicles.append(v)

    return vehicles


def load_cargos(conn: sqlite3.Connection) -> list[Cargo]:
    """Load all cargos from DB."""
    cursor = conn.cursor()
    inner = conn.cursor()
    inner2 = conn.cursor()
    cargos = []

    for row in cursor.execute("""
        SELECT c.id, c.name, c.cargo_type, c.volume_size,
               COALESCE(cw.total_weight_kg, c.weight_max, 0) as weight_kg,
               c.payment_per_km, c.payment_multiplier, c.base_payment,
               c.min_delivery_distance, c.max_delivery_distance,
               c.allow_stacking, c.fragile, c.is_deprecated
        FROM cargos c
        LEFT JOIN cargo_weights cw ON c.id = cw.cargo_id
        ORDER BY c.cargo_type, c.name
    """):
        raw_name = row[1] or ''
        # Use humanized ID when name is empty or a GUID
        if not raw_name or _is_guid(raw_name):
            display_name = _humanize_id(row[0])
        else:
            display_name = raw_name
        c = Cargo(
            id=row[0], name=display_name, cargo_type=row[2] or '',
            volume_size=row[3] or 0, weight_kg=row[4] or 0.0,
            payment_per_km=row[5] or 0, payment_multiplier=row[6] or 1.0,
            base_payment=row[7] or 0,
            min_delivery_distance=row[8] or 0, max_delivery_distance=row[9] or 0,
            allow_stacking=bool(row[10]), fragile=row[11] or 0,
            is_deprecated=bool(row[12]),
        )

        # Space types
        for st_row in inner.execute(
            "SELECT space_type FROM cargo_space_types WHERE cargo_id = ?", (c.id,)
        ):
            c.space_types.append(st_row[0])

        # Production sources
        for prod_row in inner.execute("""
            SELECT dp.id, pc.production_time_seconds
            FROM production_outputs po
            JOIN production_configs pc ON po.production_config_id = pc.id
            JOIN delivery_points dp ON pc.delivery_point_id = dp.id
            WHERE po.cargo_id = ?
        """, (c.id,)):
            # Get inputs for this production config
            inputs = []
            for inp_row in inner2.execute("""
                SELECT pi.cargo_id, pi.quantity
                FROM production_inputs pi
                JOIN production_configs pc ON pi.production_config_id = pc.id
                JOIN delivery_points dp ON pc.delivery_point_id = dp.id
                WHERE dp.id = ? AND pc.production_time_seconds = ?
            """, (prod_row[0], prod_row[1])):
                inputs.append((inp_row[0], inp_row[1]))
            c.produced_at.append((prod_row[0], inputs, prod_row[1]))

        # Consumption destinations
        for cons_row in inner.execute("""
            SELECT dp.id, pc.production_time_seconds
            FROM production_inputs pi
            JOIN production_configs pc ON pi.production_config_id = pc.id
            JOIN delivery_points dp ON pc.delivery_point_id = dp.id
            WHERE pi.cargo_id = ?
        """, (c.id,)):
            c.consumed_at.append((cons_row[0], [], cons_row[1]))

        cargos.append(c)

    return cargos


def _part_display_name(part_id: str) -> str:
    """Human-readable display name for a part derived from its key.

    The DB stores localization GUIDs for most parts (no locres in our pipeline),
    so we render the part key, inserting spaces before internal capitals to make
    e.g. 'HeavyDuty_350HP' read as 'HeavyDuty 350HP'. This matches how the wiki
    already displays part IDs in vehicle Default Parts tables.
    """
    name = part_id.replace('_', ' ')
    # Insert a space before internal capitals: 'HeavyDuty350HP' -> 'HeavyDuty 350 HP'
    name = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name or part_id


# --- Localization (Game.locres) ---
_LOCRES_CACHE: Optional[dict] = None
_PART_INDEX: dict = {}  # part_id -> Part, populated by load_parts()


def _load_locres() -> dict:
    global _LOCRES_CACHE
    if _LOCRES_CACHE is None:
        p = Path(__file__).resolve().parent.parent / "locres_map.json"
        try:
            _LOCRES_CACHE = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception:
            _LOCRES_CACHE = {}
    return _LOCRES_CACHE


_LOCALE_NAME = {
    "en": "English", "de": "Deutsch", "fr": "Français", "es-ES": "Español",
    "it": "Italiano", "ja": "日本語", "ko": "한국어", "pt-BR": "Português (BR)",
    "ru": "Русский", "zh-Hans": "简体中文", "zh-Hant": "繁體中文", "pl": "Polski",
    "tr": "Türkçe", "cs": "Čeština", "vi": "Tiếng Việt", "nl": "Nederlands",
    "sv": "Svenska", "no": "Norsk", "fi": "Suomi", "hu": "Magyar",
    "lt": "Lietuvių", "uk": "Українська", "es-419": "Español (LATAM)",
}
_LOCALE_ORDER = ["en", "de", "fr", "es-ES", "it", "ja", "ko", "pt-BR", "ru",
                 "zh-Hans", "zh-Hant", "pl", "tr", "cs", "vi", "nl", "sv",
                 "no", "fi", "hu", "lt", "uk", "es-419"]


def _part_localized(locres_key: Optional[str]) -> Optional[str]:
    """English localized name for a part's locres key, or None if absent."""
    if not locres_key:
        return None
    vp = _load_locres().get("en", {}).get("VehicleParts", {})
    return vp.get(locres_key)


def _part_localized_langs(locres_key: Optional[str]) -> list[tuple[str, str]]:
    """[(language_label, localized_name)] for languages differing from English.

    English is always first. Empty if the part has no locres entry (those parts
    show the same auto-generated English name in every language).
    """
    if not locres_key:
        return []
    data = _load_locres()
    en_vp = data.get("en", {}).get("VehicleParts", {})
    base = en_vp.get(locres_key)
    if not base:
        return []
    out = [("English", base)]
    for tag in _LOCALE_ORDER:
        if tag == "en":
            continue
        v = data.get(tag, {}).get("VehicleParts", {}).get(locres_key)
        if v and v != base:
            out.append((_LOCALE_NAME.get(tag, tag), v))
    return out


def _part_show_name(part_id: str, locres_key: Optional[str]) -> str:
    """Best display name: real localized English name when available, else humanized key."""
    localized = _part_localized(locres_key)
    return localized if localized else _part_display_name(part_id)


def _json_load(s) -> list:
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def load_parts(conn: sqlite3.Connection) -> list[Part]:
    """Load all vehicle parts plus their non-default tuning stats and install restrictions.

    Also populates the module-global _PART_INDEX (part_id -> Part) so vehicle
    pages can resolve part display names / slugs and compute installable parts.
    """
    global _PART_INDEX
    cursor = conn.cursor()
    parts = []
    for row in cursor.execute("""
        SELECT id, name, part_type, cost, mass_kg, is_hidden,
               truck_classes, truck_class_include_none, vehicle_keys,
               override_vehicle_keys, slots
        FROM vehicle_parts
        WHERE is_hidden = 0 OR is_hidden IS NULL
        ORDER BY part_type, id
    """):
        pid = row[0]
        locres_key = row[1] or None
        p = Part(
            id=pid,
            name=_part_show_name(pid, locres_key),
            locres_key=locres_key,
            part_type=row[2] or '',
            cost=row[3] or 0,
            mass_kg=row[4] or 0.0,
            is_hidden=bool(row[5]),
            truck_classes=_json_load(row[6]),
            truck_class_include_none=bool(row[7]),
            vehicle_keys=_json_load(row[8]),
            override_vehicle_keys=_json_load(row[9]),
            slots=_json_load(row[10]),
        )
        p.stats = load_part_stats(conn, pid)
        parts.append(p)

    by_id = {p.id: p for p in parts}
    for pid, vtype in cursor.execute("SELECT part_id, vehicle_type FROM part_compatible_types"):
        if pid in by_id:
            by_id[pid].vehicle_types.append(vtype)
    _PART_INDEX = by_id
    return parts


def load_part_stats(conn: sqlite3.Connection, part_id: str) -> dict:
    """Load a part's tuning stats as {struct_type: {field: value}}.

    Values equal to the per-struct-field 'default' (the mode across all parts)
    are dropped, mirroring the game's own editor-default convention so pages
    show the meaningful tuning rather than a wall of 1.0/0.0 defaults.
    """
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT struct_type, field_name, field_value FROM part_tuning WHERE part_id = ?",
        (part_id,),
    ).fetchall()
    if not rows:
        return {}
    return _filter_default_stats(conn, rows)


_default_stats_cache: dict = {}


def _filter_default_stats(conn, rows) -> dict:
    """Drop values that match the per-struct-field mode across all parts.

    The mode default for every (struct_type, field_name) is computed once over
    all of part_tuning and cached. A part's field is only emitted when its value
    differs from that default. Scalar-boolean-ish toggle fields ('bIsValid') are
    kept as-is (0/1) since the mode would swallow real differences.
    """
    cursor = conn.cursor()

    # Compute per-(struct,field) default = most common value — once.
    if not _default_stats_cache:
        mode: dict[tuple[str, str], dict] = {}
        for st, fn, fv in cursor.execute(
            "SELECT struct_type, field_name, field_value FROM part_tuning"
        ):
            key = (st, fn)
            v = _norm_stat(fv)
            bucket = mode.setdefault(key, {})
            bucket[v] = bucket.get(v, 0) + 1
        _default_stats_cache.update(
            {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in mode.items()}
        )

    stats: dict[str, dict] = {}
    for struct_type, field_name, field_value in rows:
        # Skip boolean-toggle fields (bIsValid, bIsDualRearWheel...) — they mean
        # "this optional sub-struct is present" and are noise as 0/1 rows.
        if str(field_name).startswith('bIs'):
            continue
        key = (struct_type, field_name)
        val = _norm_stat(field_value)
        if val == _default_stats_cache.get(key):
            continue
        stats.setdefault(struct_type, {})[field_name] = val
    return stats


def _norm_stat(value):
    """Normalize a stat value for comparison (floats as float, strings as-is)."""
    if isinstance(value, float) and value == int(value):
        return int(value)
    return value


# ---------------------------------------------------------------------------
# Content Generators
# ---------------------------------------------------------------------------

def _fmt_cost(cost: int) -> str:
    """Format cost with comma separators."""
    return f"{cost:,}"


def _fmt_weight(kg: float) -> str:
    """Format weight in kg."""
    if kg == int(kg):
        return f"{int(kg):,} kg"
    return f"{kg:,.1f} kg"


def _fmt_type(raw: str) -> str:
    """Humanize CamelCase type strings.
    
    'HeavyDuty' -> 'Heavy duty'
    'SemiTractor' -> 'Semi tractor'
    'SmallTrailer' -> 'Small trailer'
    """
    if not raw or raw == 'None':
        return ''
    # Insert space before uppercase letters (but not at start or consecutive)
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', raw)
    # Capitalize first word, lowercase rest
    return spaced[0].upper() + spaced[1:].lower() if spaced else raw


def _name_to_slug(name: str) -> str:
    """Convert a display name to a wiki page slug."""
    # 'Air City' -> 'air_city', 'Atlas 6x2 Dry Van' -> 'atlas_6x2_dry_van'
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def _cargo_slug(cargo_id: str) -> str:
    """Convert cargo ID to wiki page slug."""
    return cargo_id.lower().replace(' ', '_')


_GUID_RE = re.compile(r'^[0-9A-Fa-f]{20,}$')


def _is_guid(s: str) -> bool:
    """Check if a string looks like an Unreal Engine GUID."""
    return bool(_GUID_RE.match(s))


def _humanize_id(cargo_id: str) -> str:
    """Convert CamelCase/underscore ID to human-readable name.
    
    'AirlineMealPallet' -> 'Airline Meal Pallet'
    'Log_Oak_12ft' -> 'Log Oak 12ft'
    """
    # Replace underscores with spaces
    s = cargo_id.replace('_', ' ')
    # Insert space before uppercase letters
    s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)
    # Clean up double spaces
    s = re.sub(r'  +', ' ', s).strip()
    return s


def build_slug_map(wiki_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Build mappings from DB vehicle ID (Internal key) to wiki page slug and display name.
    
    Scans existing vehicle pages for 'Internal key = X' and 'name = X' lines.
    Returns (slug_map, name_map) where:
      slug_map: {internal_key: slug}
      name_map: {internal_key: display_name}
    """
    slug_map = {}  # internal_key -> slug
    name_map = {}  # internal_key -> display_name from wiki
    vehicles_dir = wiki_dir / 'vehicles'
    if not vehicles_dir.exists():
        return slug_map, name_map
    
    for page_path in vehicles_dir.glob('*.txt'):
        slug = page_path.stem  # e.g. 'air_city'
        try:
            text = page_path.read_text(encoding='utf-8')
        except Exception:
            continue
        
        internal_key = None
        display_name = None
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('Internal key = '):
                internal_key = stripped[len('Internal key = '):].strip()
            elif stripped.startswith('name = ') and display_name is None:
                display_name = stripped[len('name = '):].strip()
        
        if internal_key:
            slug_map[internal_key] = slug
            if display_name:
                name_map[internal_key] = display_name
    
    return slug_map, name_map


def _get_drivetrain(parts: list[tuple[str, str]]) -> str:
    """Infer drivetrain from default LSD parts."""
    # Collect unique LSD slot base numbers
    lsd_slots = set()
    for slot, _ in parts:
        if slot.startswith('LSD'):
            # LSD0 = rear, LSD1 = front (both present = AWD)
            lsd_slots.add(slot)
    
    has_front = any(s in lsd_slots for s in ('LSD1', 'LSD_Front'))
    has_rear = any(s in lsd_slots for s in ('LSD0', 'LSD_Rear', 'LSD'))
    
    if has_front and has_rear:
        return 'AWD'
    if has_front:
        return 'Front-wheel drive'
    if has_rear:
        return 'Rear-wheel drive'
    # Fallback: check if ANY LSD exists
    if lsd_slots:
        return 'Rear-wheel drive'
    return ''


def _group_parts(parts: list[tuple[str, str]]) -> list[tuple[str, str, int]]:
    """Group identical parts across numbered slots. Returns (slot_base, part_id, count)."""
    from collections import OrderedDict
    groups: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
    for slot, part_id in parts:
        # Strip trailing digits: Tire0, Tire1 -> Tire
        base = re.sub(r'\d+$', '', slot)
        key = (base, part_id)
        if key not in groups:
            groups[key] = []
        groups[key].append((slot, part_id))

    result = []
    for (base, part_id), entries in groups.items():
        result.append((base, part_id, len(entries)))
    return result


def generate_vehicle_infobox(v: Vehicle, existing_image: Optional[str] = None) -> str:
    """Generate the infobox section for a vehicle."""
    lines = ["{{infobox>"]
    lines.append(f"name = {v.name}")
    if existing_image:
        lines.append(existing_image)
    lines.append(f"Internal key = {v.id}")

    vtype = _fmt_type(v.vehicle_type)
    tclass = _fmt_type(v.truck_class)
    type_str = f"{vtype}, {tclass}" if tclass else vtype
    lines.append(f"Type = {type_str}")

    lines.append(f"Cost = {_fmt_cost(v.cost)}")
    lines.append(f"Weight = {_fmt_weight(v.chassis_mass_kg)}")

    if v.engine_hp:
        lines.append(f"Engine = {v.engine_hp} HP")

    drivetrain = _get_drivetrain(v.default_parts)
    if drivetrain:
        lines.append(f"Drivetrain = {drivetrain}")

    if v.cargo_space_type:
        lines.append(f"Cargo space = {v.cargo_space_type}")

    if v.air_drag and v.air_drag != 1.0:
        lines.append(f"Drag coefficient = {v.air_drag}")

    lines.append("}}")
    return '\n'.join(lines)


def generate_vehicle_heading(v: Vehicle) -> str:
    """Generate vehicle page heading."""
    vtype = _fmt_type(v.vehicle_type).lower()
    tclass = _fmt_type(v.truck_class).lower()
    type_desc = f"{tclass} {vtype}" if tclass else vtype

    return f"====== {v.name} ======\n**{v.name}** is a {type_desc} vehicle in [[:motor_town|Motor Town]]"


def generate_vehicle_specs(v: Vehicle) -> str:
    """Generate the specifications section."""
    lines = ["===== Specifications ====="]

    # Key stats table
    lines.append("^ Stat ^ Value ^")

    # Engine
    if v.engine_id:
        hp_str = f" ({v.engine_hp} HP)" if v.engine_hp else ""
        ep = _PART_INDEX.get(v.engine_id)
        edisp = ep.name if ep else _part_display_name(v.engine_id)
        lines.append(f"| Engine | [[parts:{_part_slug(v.engine_id)}|{edisp}]]{hp_str} |")

    # Transmission
    transmission = next((pid for slot, pid in v.default_parts if slot == 'Transmission'), None)
    if transmission:
        tp = _PART_INDEX.get(transmission)
        tdisp = tp.name if tp else _part_display_name(transmission)
        lines.append(f"| Transmission | [[parts:{_part_slug(transmission)}|{tdisp}]] |")

    # Drivetrain
    drivetrain = _get_drivetrain(v.default_parts)
    if drivetrain:
        lines.append(f"| Drivetrain | {drivetrain} |")

    # Final drive ratio
    if v.final_drive_ratio:
        lines.append(f"| Final Drive Ratio | {v.final_drive_ratio} |")

    # Weights
    lines.append(f"| Chassis Weight | {_fmt_weight(v.chassis_mass_kg)} |")
    if v.total_weight_kg > 0:
        lines.append(f"| Total Weight (stock) | {_fmt_weight(v.total_weight_kg)} |")
    if v.air_drag and v.air_drag != 1.0:
        lines.append(f"| Drag Coefficient | {v.air_drag} |")

    # Cargo Space
    if v.cargo_space_type:
        lines.append("")
        lines.append("===== Cargo Space =====")
        lines.append("^ Stat ^ Value ^")
        lines.append(f"| Type | {v.cargo_space_type} |")
        if v.cargo_length_m:
            lines.append(f"| Length | {v.cargo_length_m} m |")
        if v.cargo_width_m:
            lines.append(f"| Width | {v.cargo_width_m} m |")
        if v.cargo_height_m:
            lines.append(f"| Height | {v.cargo_height_m} m |")
        if v.cargo_volume_m3:
            lines.append(f"| Volume | {v.cargo_volume_m3} m³ |")
        if v.cargo_dump_volume_kl:
            lines.append(f"| Dump Volume | {v.cargo_dump_volume_kl} kL |")
        if v.cargo_fix:
            lines.append("| Fixed Cargo | Yes |")
        if v.cargo_unlimited_height:
            lines.append("| Unlimited Height | Yes |")

    # Capabilities
    capabilities = []
    if v.is_taxiable:
        capabilities.append("Taxi")
    if v.is_limoable:
        capabilities.append("Limousine")
    if v.is_busable:
        capabilities.append("Bus")
    if v.is_race_car:
        capabilities.append("Race car")
    if v.can_haul_trailer:
        capabilities.append("Can haul trailer")
    if v.has_fuel_pump:
        capabilities.append("Has fuel pump")

    if capabilities:
        lines.append("")
        lines.append("===== Capabilities =====")
        for cap in capabilities:
            lines.append(f"  * {cap}")

    # Delivery info
    if v.delivery_payment_multiplier != 1.0 or v.delivery_base_payment:
        lines.append("")
        lines.append("===== Delivery =====")
        lines.append("^ Stat ^ Value ^")
        if v.delivery_payment_multiplier != 1.0:
            lines.append(f"| Payment Multiplier | {v.delivery_payment_multiplier}x |")
        if v.delivery_base_payment:
            lines.append(f"| Base Payment | ${v.delivery_base_payment} |")

    # Default Parts table
    grouped = _group_parts(v.default_parts)
    if grouped:
        lines.append("")
        lines.append("===== Default Parts =====")
        lines.append("^ Slot ^ Part ^ Mass ^")
        for base, part_id, count in grouped:
            count_str = f" (×{count})" if count > 1 else ""
            pp = _PART_INDEX.get(part_id)
            disp = pp.name if pp else _part_display_name(part_id)
            mass = _fmt_weight(pp.mass_kg) if (pp and pp.mass_kg) else "—"
            lines.append(f"| {base} | [[parts:{_part_slug(part_id)}|{disp}]]{count_str} | {mass} |")

    # Installable Parts (aggregate computed from part-side vehicle restrictions)
    installable = _installable_for_vehicle(v)
    if installable:
        lines.append("")
        lines.append(f"===== Installable Parts ({sum(len(x) for x in installable.values())}) =====")
        for type_name in sorted(installable.keys()):
            plist = installable[type_name]
            lines.append(f"==== {type_name} ({len(plist)}) ====")
            cap = 40
            for pp in plist[:cap]:
                lines.append(f"  * [[parts:{_part_slug(pp.id)}|{pp.name}]]")
            if len(plist) > cap:
                lines.append(f"  * … and {len(plist) - cap} more")
        lines.append("")

    return '\n'.join(lines)


def _part_fits(v, p: Part, veh_truck: str) -> bool:
    """Whether part p can be installed on vehicle v (part-side restriction model)."""
    if p.is_hidden:
        return False
    # OverrideAllowedVehicleKeys is an escape hatch that wins over every rule.
    if v.id in p.override_vehicle_keys:
        return True
    # VehicleTypes: empty = no filter; else the vehicle's type must be present.
    if p.vehicle_types and (v.vehicle_type or '') not in p.vehicle_types:
        return False
    # TruckClasses: empty = no filter; else truck_class must match (None also ok if include-none).
    if p.truck_classes:
        ok = veh_truck in p.truck_classes
        if not ok and p.truck_class_include_none and veh_truck in ('', 'None'):
            ok = True
        if not ok:
            return False
    # VehicleKeys: empty = no filter; else vehicle id must be listed.
    if p.vehicle_keys and v.id not in p.vehicle_keys:
        return False
    return True


def _installable_for_vehicle(v) -> dict[str, list]:
    """All parts installable on vehicle v, grouped by part-type display name.

    Empty when _PART_INDEX is not populated (e.g. a vehicles-only sync run).
    """
    if not _PART_INDEX:
        return {}
    veh_truck = (v.truck_class or '').strip()
    result: dict[str, list] = {}
    for p in _PART_INDEX.values():
        if not _part_fits(v, p, veh_truck):
            continue
        tn = _part_type_name(p.part_type)
        if tn == 'Unknown':
            tn = p.part_type or 'Other'
        result.setdefault(tn, []).append(p)
    for tn in result:
        result[tn].sort(key=lambda x: _natural_part_key(x.id))
    return result


def generate_cargo_page(c: Cargo) -> str:
    """Generate a full cargo page."""
    parts = []

    # Infobox
    infobox = [
        "{{infobox>",
        f"name = {c.name}",
        f"Cargo Type = {c.cargo_type}",
        f"Volume = {c.volume_size}",
        f"Weight = {_fmt_weight(c.weight_kg)}",
    ]
    if c.payment_per_km:
        infobox.append(f"Payment = ${c.payment_per_km}/km")
    infobox.append("}}")
    parts.append('\n'.join(infobox))

    # Heading
    parts.append("")
    parts.append(f"====== {c.name} ======")
    parts.append("")

    # Specs
    specs = [
        "===== Specifications =====",
        "^ Stat ^ Value ^",
        f"| Type | {c.cargo_type} |",
        f"| Weight | {_fmt_weight(c.weight_kg)} |",
    ]
    if c.payment_per_km:
        specs.append(f"| Payment per km | ${c.payment_per_km} |")
    if c.payment_multiplier and c.payment_multiplier != 1.0:
        specs.append(f"| Payment multiplier | {c.payment_multiplier} |")
    if c.base_payment:
        specs.append(f"| Base payment | ${c.base_payment} |")
    if c.min_delivery_distance:
        specs.append(f"| Min delivery distance | {c.min_delivery_distance}m |")
    if c.max_delivery_distance:
        specs.append(f"| Max delivery distance | {c.max_delivery_distance}m |")
    specs.append(f"| Stackable | {'Yes' if c.allow_stacking else 'No'} |")
    if c.fragile:
        specs.append(f"| Fragile | Level {c.fragile} |")

    if c.space_types:
        specs.append("")
        specs.append("===== Compatible Cargo Space Types =====")
        for st in c.space_types:
            specs.append(f"  * {st}")


    parts.append('\n'.join(specs))

    # User placeholder
    parts.append("")
    parts.append("===== Notes =====")
    parts.append("")

    # Production
    if c.produced_at or c.consumed_at:
        prod_lines = ["===== Production ====="]
        if c.produced_at:
            prod_lines.append("==== Produced At ====")
            prod_lines.append("^ Location ^ Inputs ^ Time ^")
            for loc, inputs, time_s in c.produced_at:
                input_str = ', '.join(f"{qty}× {cid}" for cid, qty in inputs) if inputs else '(passive)'
                time_str = f"{time_s}s" if time_s else '—'
                prod_lines.append(f"| {loc} | {input_str} | {time_str} |")

        if c.consumed_at:
            prod_lines.append("==== Consumed At ====")
            prod_lines.append("^ Location ^ Time ^")
            for loc, _, time_s in c.consumed_at:
                time_str = f"{time_s}s" if time_s else '—'
                prod_lines.append(f"| {loc} | {time_str} |")


        parts.append('\n'.join(prod_lines))

    return '\n'.join(parts) + '\n'


_PART_TYPE_ENGLISH = {
    'AeroParts': 'Aero', 'AngleKit': 'Angle Kit', 'AntiRollBar': 'Anti-Roll Bar',
    'Body': 'Body', 'BrakeBalance': 'Brake Balance', 'BrakePad': 'Brake Pad',
    'BrakePower': 'Brake Power', 'CargoBed': 'Cargo Bed', 'CargoBedAttachment': 'Cargo Bed Attachment',
    'CoolantRadiator': 'Coolant Radiator', 'Engine': 'Engine', 'FinalDriveRatio': 'Final Drive Ratio',
    'Fender': 'Fender', 'FrontBumper': 'Front Bumper', 'FrontSpoiler': 'Front Spoiler',
    'FrontWindowSticker': 'Front Window Sticker', 'FrontWindowSunVisor': 'Sun Visor',
    'Headlight': 'Headlight', 'Intake': 'Intake', 'LSD': 'Limited Slip Differential',
    'RearBumper': 'Rear Bumper', 'RearSpoiler': 'Rear Spoiler', 'RearWindowLouvers': 'Rear Window Louvers',
    'RearWing': 'Rear Wing', 'Roof': 'Roof', 'RoofRack': 'Roof Rack',
    'SideSkirt': 'Side Skirt', 'Suspension_Damper': 'Suspension Damper',
    'Suspension_Spring': 'Suspension Spring', 'Suspension_RideHeight': 'Suspension Ride Height',
    'TaxiLicense': 'Taxi License', 'BusLicense': 'Bus License', 'EscortLicense': 'Escort License',
    'Tire': 'Tire', 'TrailerHitch': 'Trailer Hitch', 'Transmission': 'Transmission',
    'Trunk': 'Trunk', 'Turbocharger': 'Turbocharger', 'Utility': 'Utility',
    'Wheel': 'Wheel', 'WheelSpacer': 'Wheel Spacer', 'Winch': 'Winch',
    'Attachment': 'Attachment', 'Bullbar': 'Bullbar',
}


def _part_type_name(part_type: str) -> str:
    """Human-readable part type name (English)."""
    if part_type in _PART_TYPE_ENGLISH:
        return _PART_TYPE_ENGLISH[part_type]
    if not part_type:
        return 'Unknown'
    return part_type.replace('_', ' ')


def _part_slug(part_id: str) -> str:
    """Slug for a part page URL (must be a valid DokuWiki page ID).

    DokuWiki page IDs allow [a-z0-9 _ - . :] but NOT '+'. Map '+' to 'p' so
    'RideHeight_+1' -> 'rideheight_p1' stays distinct from 'RideHeight_-1' ->
    'rideheight_-1' (the '-' is legal and kept). Without this, DokuWiki strips
    the '+' from links and resolves them to a non-existent page.
    """
    slug = part_id.lower().replace('+', 'p')
    slug = re.sub(r'[^a-z0-9_\-]+', '_', slug)
    return slug.strip('_')


def _natural_part_key(pid: str):
    """Sort key giving numeric ordering (small -> large) where parts are named
    by magnitude (e.g. Damper 50, 80, 120; Ride Height -1 .. +20), and plain
    alphabetical order for everything else.
    """
    nums = [int(m) for m in re.findall(r'([+-]?\d+)', pid)]
    if nums:
        return (0, nums, pid.lower())
    return (1, [], pid.lower())


def generate_part_page(p: Part) -> str:
    """Generate a full part wiki page."""
    parts = []

    # Infobox
    infobox = [
        "{{infobox>",
        f"name = {p.name}",
        f"Part Type = {_part_type_name(p.part_type)}",
        f"Cost = {_fmt_cost(p.cost)}",
    ]
    if p.mass_kg:
        infobox.append(f"Mass = {_fmt_weight(p.mass_kg)}")
    infobox.append("}}")
    parts.append('\n'.join(infobox))
    parts.append("")

    # Heading
    parts.append(f"====== {p.name} ======")
    parts.append("")
    type_lower = _part_type_name(p.part_type).lower()
    article = 'an' if type_lower[:1] in ('a', 'e', 'i', 'o', 'u') else 'a'
    parts.append(f"**{p.name}** is {article} {type_lower} part for vehicles in [[:motor_town|Motor Town]].")
    parts.append("")

    # In other languages (real localized names from Game.locres; only when a
    # translation exists — parts without a locres entry show the same
    # auto-generated English name in every language).
    i18n = _part_localized_langs(p.locres_key)
    if i18n:
        i18n_lines = ["===== In other languages =====", "^ Language ^ Name ^"]
        for label, name in i18n:
            i18n_lines.append(f"| {label} | {name} |")
        parts.append('\n'.join(i18n_lines))
        parts.append("")

    # Specs
    specs = [
        "===== Specifications =====",
        "^ Stat ^ Value ^",
        f"| Type | {_part_type_name(p.part_type)} |",
        f"| Cost | {_fmt_cost(p.cost)} |",
    ]
    if p.mass_kg:
        specs.append(f"| Mass | {_fmt_weight(p.mass_kg)} |")
    parts.append('\n'.join(specs))
    parts.append("")

    # Stats (tuning)
    if p.stats:
        stat_lines = ["===== Stats ====="]
        for struct in sorted(p.stats.keys()):
            head = _part_type_name(struct)
            if head == 'Unknown':
                head = struct
            stat_lines.append(f"==== {head} ====")
            stat_lines.append("^ Parameter ^ Value ^")
            for field, value in sorted(p.stats[struct].items()):
                stat_lines.append(f"| {_display_field(field)} | {_display_value(value)} |")
        parts.append('\n'.join(stat_lines))
        parts.append("")

    # User placeholder
    parts.append("===== Notes =====")
    parts.append("")

    return '\n'.join(parts) + '\n'


def _display_field(field: str) -> str:
    """Humanize a stat field name: 'MaxTorque' -> 'Max Torque'."""
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', field).replace('_', ' ').strip() or field


def _display_value(value) -> str:
    """Format a stat value for the wiki."""
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.2f}".rstrip('0').rstrip('.')
    return str(value)


def generate_parts_index(parts: list[Part]) -> str:
    """Generate a part index page grouped by part type."""
    lines = [
        "====== List of Vehicle Parts (Auto-Generated) ======",
        "",
        f"There are {len(parts)} vehicle parts in [[:motor_town|Motor Town]].",
        "",
    ]

    by_type: dict[str, list[Part]] = {}
    for p in parts:
        pt = p.part_type or 'Other'
        by_type.setdefault(pt, []).append(p)

    for pt in sorted(by_type.keys()):
        type_name = _part_type_name(pt)
        lines.append(f"===== {type_name} =====")
        lines.append("^ Part ^ Cost ^ Mass ^")
        for p in sorted(by_type[pt], key=lambda x: _natural_part_key(x.id)):
            slug = _part_slug(p.id)
            mass = _fmt_weight(p.mass_kg) if p.mass_kg else '—'
            lines.append(f"| [[parts:{slug}|{p.name}]] | {_fmt_cost(p.cost)} | {mass} |")
        lines.append("")

    return '\n'.join(lines) + '\n'


def generate_vehicle_index(vehicles: list[Vehicle], slug_map: dict[str, str]) -> str:
    """Generate a vehicle index page grouped by type."""
    lines = [
        "====== List of Vehicles (Auto-Generated) ======",
        "",
        f"There are {len(vehicles)} vehicles in [[:motor_town|Motor Town]].",
        "",
    ]

    # Group by type
    by_type: dict[str, list[Vehicle]] = {}
    for v in vehicles:
        vtype = v.vehicle_type or 'Other'
        if vtype not in by_type:
            by_type[vtype] = []
        by_type[vtype].append(v)

    for vtype in sorted(by_type.keys()):
        lines.append(f"===== {vtype} =====")
        for v in sorted(by_type[vtype], key=lambda x: x.name):
            slug = slug_map.get(v.id, _name_to_slug(v.name))
            lines.append(f"  * [[vehicles:{slug}|{v.name}]]")
        lines.append("")


    return '\n'.join(lines) + '\n'


def generate_vehicle_comparison(vehicles: list[Vehicle], slug_map: dict[str, str]) -> str:
    """Generate a full vehicle comparison table."""
    lines = [
        "====== Vehicle Comparison Table (Auto-Generated) ======",
        "",
        "^ Name ^ Type ^ Cost ^ Drivetrain ^ Chassis Weight ^ Total Weight ^ Drag ^",
    ]

    for v in sorted(vehicles, key=lambda x: (x.vehicle_type, x.name)):
        slug = slug_map.get(v.id, _name_to_slug(v.name))
        drivetrain = _get_drivetrain(v.default_parts)
        lines.append(
            f"| [[vehicles:{slug}|{v.name}]] "
            f"| {v.vehicle_type} "
            f"| {_fmt_cost(v.cost)} "
            f"| {drivetrain} "
            f"| {_fmt_weight(v.chassis_mass_kg)} "
            f"| {_fmt_weight(v.total_weight_kg)} "
            f"| {v.air_drag} |"
        )


    return '\n'.join(lines) + '\n'


def generate_cargo_index(cargos: list[Cargo]) -> str:
    """Generate a cargo index page."""
    active = [c for c in cargos if not c.is_deprecated]
    lines = [
        "====== List of Cargos ======",
        "",
        f"There are {len(active)} active cargos in [[:motor_town|Motor Town]].",
        "",
        "^ Name ^ Type ^ Weight ^ Payment/km ^",
    ]

    for c in sorted(active, key=lambda x: (x.cargo_type, x.name)):
        slug = _cargo_slug(c.id)
        lines.append(
            f"| [[cargo:{slug}|{c.name}]] "
            f"| {c.cargo_type} "
            f"| {_fmt_weight(c.weight_kg)} "
            f"| ${c.payment_per_km} |"
        )


    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# Merger
# ---------------------------------------------------------------------------

def merge_vehicle_page(
    existing_text: str | None,
    vehicle: Vehicle,
) -> str:
    """Merge system-generated content with existing user content for a vehicle page."""

    if existing_text is None:
        # Brand new page — generate with placeholders
        return _build_fresh_vehicle_page(vehicle)

    sections = parse_page(existing_text)

    # Extract image from existing infobox
    existing_image = None
    for sec in sections:
        if sec.name == 'infobox':
            existing_image = extract_infobox_image(sec.content)
            break

    # Build the merged page
    parts = []

    # 1. Infobox
    parts.append(generate_vehicle_infobox(vehicle, existing_image))
    parts.append("")

    # 2. Heading
    parts.append(generate_vehicle_heading(vehicle))
    parts.append("")

    # 3. User body content (preserved from existing page)
    for sec in sections:
        if sec.is_user:
            parts.append(sec.content)
            parts.append("")

    # 4. Specs (regenerated)
    parts.append(generate_vehicle_specs(vehicle))
    parts.append("")

    # 5. Axle section (preserved from existing)
    for sec in sections:
        if sec.name == 'axles':
            parts.append(sec.content)
            parts.append("")
            break

    # 6. i18n section (preserved from existing)
    for sec in sections:
        if sec.name == 'i18n':
            parts.append(sec.content)
            break

    result = '\n'.join(parts)
    # Clean up excessive blank lines
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.rstrip() + '\n'


def _build_fresh_vehicle_page(vehicle: Vehicle) -> str:
    """Build a brand new vehicle page with placeholders."""
    parts = []

    parts.append(generate_vehicle_infobox(vehicle))
    parts.append("")
    parts.append(generate_vehicle_heading(vehicle))
    parts.append("")
    parts.append(generate_vehicle_specs(vehicle))
    parts.append("")
    parts.append("===== Overview =====")
    parts.append("")
    parts.append("===== Tips & Strategies =====")
    parts.append("")

    return '\n'.join(parts).rstrip() + '\n'


# ---------------------------------------------------------------------------
# Sync Engine
# ---------------------------------------------------------------------------

def sync_vehicles(
    conn: sqlite3.Connection,
    wiki_dir: Path,
    slug_map: dict[str, str],
    name_map: dict[str, str],
    dry_run: bool = False,
    vehicle_filter: str | None = None,
) -> dict:
    """Sync all vehicle pages. Returns stats dict."""
    vehicles = load_vehicles(conn)
    vehicles_dir = wiki_dir / 'vehicles'

    # Resolve display names from wiki for vehicles with bad DB names
    for v in vehicles:
        if v.id in name_map:
            # Always prefer the wiki-curated display name
            v.name = name_map[v.id]

    stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': 0}

    if not dry_run:
        vehicles_dir.mkdir(parents=True, exist_ok=True)

    for v in vehicles:
        if vehicle_filter and v.id != vehicle_filter:
            continue

        slug = slug_map.get(v.id, _name_to_slug(v.name))
        page_path = vehicles_dir / f"{slug}.txt"

        existing_text = None
        if page_path.exists():
            existing_text = page_path.read_text(encoding='utf-8')

        try:
            new_text = merge_vehicle_page(existing_text, v)
        except Exception as e:
            print(f"  ERROR: {v.id}: {e}")
            stats['errors'] += 1
            continue

        if existing_text == new_text:
            stats['unchanged'] += 1
            continue

        if existing_text is None:
            action = "CREATE"
            stats['created'] += 1
        else:
            action = "UPDATE"
            stats['updated'] += 1

        if dry_run:
            print(f"  {action}: vehicles/{slug}.txt")
            if existing_text:
                # Show a brief diff summary
                old_lines = existing_text.split('\n')
                new_lines = new_text.split('\n')
                print(f"    {len(old_lines)} → {len(new_lines)} lines")
        else:
            page_path.write_text(new_text, encoding='utf-8')
            print(f"  {action}: vehicles/{slug}.txt")

    return stats


def sync_cargos(
    conn: sqlite3.Connection,
    wiki_dir: Path,
    dry_run: bool = False,
) -> dict:
    """Sync all cargo pages. Returns stats dict."""
    cargos = load_cargos(conn)
    cargo_dir = wiki_dir / 'cargo'

    stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': 0}

    if not dry_run:
        cargo_dir.mkdir(parents=True, exist_ok=True)

    for c in cargos:
        if c.is_deprecated:
            continue

        slug = _cargo_slug(c.id)
        page_path = cargo_dir / f"{slug}.txt"

        existing_text = None
        if page_path.exists():
            existing_text = page_path.read_text(encoding='utf-8')

        try:
            new_text = generate_cargo_page(c)

        except Exception as e:
            print(f"  ERROR: {c.id}: {e}")
            stats['errors'] += 1
            continue

        if existing_text == new_text:
            stats['unchanged'] += 1
            continue

        if existing_text is None:
            action = "CREATE"
            stats['created'] += 1
        else:
            action = "UPDATE"
            stats['updated'] += 1

        if dry_run:
            print(f"  {action}: cargo/{slug}.txt")
        else:
            page_path.write_text(new_text, encoding='utf-8')
            print(f"  {action}: cargo/{slug}.txt")

    return stats


def sync_indexes(
    conn: sqlite3.Connection,
    wiki_dir: Path,
    slug_map: dict[str, str],
    name_map: dict[str, str],
    dry_run: bool = False,
) -> dict:
    """Sync index/comparison pages. Returns stats dict."""
    vehicles = load_vehicles(conn)
    cargos = load_cargos(conn)
    stats = {'created': 0, 'updated': 0, 'unchanged': 0}

    # Apply wiki display names
    for v in vehicles:
        if v.id in name_map:
            v.name = name_map[v.id]

    index_pages = {
        'list_of_vehicles_data.txt': generate_vehicle_index(vehicles, slug_map),
        'vehicle_comparison_data.txt': generate_vehicle_comparison(vehicles, slug_map),
        'list_of_cargos.txt': generate_cargo_index(cargos),
    }

    for filename, content in index_pages.items():
        page_path = wiki_dir / filename
        existing = page_path.read_text(encoding='utf-8') if page_path.exists() else None

        if existing == content:
            stats['unchanged'] += 1
            continue

        if existing is None:
            action = "CREATE"
            stats['created'] += 1
        else:
            action = "UPDATE"
            stats['updated'] += 1

        if dry_run:
            print(f"  {action}: {filename}")
        else:
            page_path.write_text(content, encoding='utf-8')
            print(f"  {action}: {filename}")

    return stats


def sync_parts(
    conn: sqlite3.Connection,
    wiki_dir: Path,
    dry_run: bool = False,
    part_filter: str | None = None,
) -> dict:
    """Sync all vehicle-part pages. Returns stats dict."""
    parts = load_parts(conn)
    parts_dir = wiki_dir / 'parts'

    stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': 0}

    if not dry_run:
        parts_dir.mkdir(parents=True, exist_ok=True)

    for p in parts:
        if part_filter and p.id != part_filter:
            continue

        slug = _part_slug(p.id)
        page_path = parts_dir / f"{slug}.txt"

        existing_text = None
        if page_path.exists():
            existing_text = page_path.read_text(encoding='utf-8')

        try:
            new_text = generate_part_page(p)
        except Exception as e:
            print(f"  ERROR: {p.id}: {e}")
            stats['errors'] += 1
            continue

        if existing_text == new_text:
            stats['unchanged'] += 1
            continue

        if existing_text is None:
            action = "CREATE"
            stats['created'] += 1
        else:
            action = "UPDATE"
            stats['updated'] += 1

        if dry_run:
            print(f"  {action}: parts/{slug}.txt")
        else:
            page_path.write_text(new_text, encoding='utf-8')
            print(f"  {action}: parts/{slug}.txt")

    return stats


def sync_parts_index(
    conn: sqlite3.Connection,
    wiki_dir: Path,
    dry_run: bool = False,
) -> dict:
    """Sync the list_of_parts index page."""
    parts = load_parts(conn)
    stats = {'created': 0, 'updated': 0, 'unchanged': 0}

    content = generate_parts_index(parts)
    filename = 'list_of_parts.txt'
    page_path = wiki_dir / filename
    existing = page_path.read_text(encoding='utf-8') if page_path.exists() else None

    if existing == content:
        stats['unchanged'] += 1
        return stats
    elif existing is None:
        action = "CREATE"
        stats['created'] += 1
    else:
        action = "UPDATE"
        stats['updated'] += 1

    if dry_run:
        print(f"  {action}: {filename}")
    else:
        page_path.write_text(content, encoding='utf-8')
        print(f"  {action}: {filename}")

    return stats


# ---------------------------------------------------------------------------
# Annie's Wiki Sync
# ---------------------------------------------------------------------------

SYSTEM_MARKER_START_RE = re.compile(r'^<!-- SYSTEM:(\w+) -->\s*$')
SYSTEM_MARKER_END_RE = re.compile(r'^<!-- /SYSTEM:(\w+) -->\s*$')
USER_MARKER_START_RE = re.compile(r'^<!-- USER:(\w+) -->\s*$')
USER_MARKER_END_RE = re.compile(r'^<!-- /USER:(\w+) -->\s*$')


def _extract_user_sections(text: str) -> dict[str, str]:
    """Parse existing Annie wiki content and extract user-contributed sections."""
    sections: dict[str, str] = {}
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        m = USER_MARKER_START_RE.match(lines[i])
        if m:
            section_name = m.group(1)
            i += 1
            content_lines = []
            while i < len(lines):
                if USER_MARKER_END_RE.match(lines[i]):
                    i += 1
                    break
                content_lines.append(lines[i])
                i += 1
            sections[section_name] = '\n'.join(content_lines)
        else:
            i += 1
    return sections


def _generate_annie_vehicle_content(v: Vehicle, user_sections: dict[str, str] | None = None) -> str:
    """Generate vehicle page content with SYSTEM/USER section markers for Annie's wiki."""
    user_sections = user_sections or {}
    parts = []

    # System: infobox
    parts.append("<!-- SYSTEM:infobox -->")
    parts.append(generate_vehicle_infobox(v))
    parts.append("<!-- /SYSTEM:infobox -->")
    parts.append("")

    # Heading
    parts.append(generate_vehicle_heading(v))
    parts.append("")

    # User: body (preserved or placeholder)
    parts.append("<!-- USER:body -->")
    body = user_sections.get("body", "").strip()
    if body:
        parts.append(body)
    parts.append("<!-- /USER:body -->")
    parts.append("")

    # System: specs (regenerated)
    parts.append("<!-- SYSTEM:specs -->")
    parts.append(generate_vehicle_specs(v))
    parts.append("<!-- /SYSTEM:specs -->")
    parts.append("")

    # User: notes (preserved or placeholder)
    parts.append("<!-- USER:notes -->")
    notes = user_sections.get("notes", "").strip()
    if notes:
        parts.append(notes)
    parts.append("<!-- /USER:notes -->")

    result = '\n'.join(parts)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.rstrip() + '\n'


def _generate_annie_cargo_content(c: Cargo, user_sections: dict[str, str] | None = None) -> str:
    """Generate cargo page content with SYSTEM/USER section markers for Annie's wiki."""
    user_sections = user_sections or {}
    parts = []

    # System: infobox
    parts.append("<!-- SYSTEM:infobox -->")
    infobox_lines = [
        "{{infobox>",
        f"name = {c.name}",
        f"Cargo Type = {c.cargo_type}",
        f"Volume = {c.volume_size}",
        f"Weight = {_fmt_weight(c.weight_kg)}",
    ]
    if c.payment_per_km:
        infobox_lines.append(f"Payment = ${c.payment_per_km}/km")
    infobox_lines.append("}}")
    parts.append('\n'.join(infobox_lines))
    parts.append("<!-- /SYSTEM:infobox -->")
    parts.append("")

    # Heading
    parts.append(f"====== {c.name} ======")
    parts.append("")

    # System: specs
    parts.append("<!-- SYSTEM:specs -->")
    specs = [
        "===== Specifications =====",
        "^ Stat ^ Value ^",
        f"| Type | {c.cargo_type} |",
        f"| Weight | {_fmt_weight(c.weight_kg)} |",
    ]
    if c.payment_per_km:
        specs.append(f"| Payment per km | ${c.payment_per_km} |")
    if c.payment_multiplier and c.payment_multiplier != 1.0:
        specs.append(f"| Payment multiplier | {c.payment_multiplier} |")
    if c.base_payment:
        specs.append(f"| Base payment | ${c.base_payment} |")
    specs.append(f"| Stackable | {'Yes' if c.allow_stacking else 'No'} |")
    if c.fragile:
        specs.append(f"| Fragile | Level {c.fragile} |")
    if c.space_types:
        specs.append("")
        specs.append("===== Compatible Cargo Space Types =====")
        for st in c.space_types:
            specs.append(f"  * {st}")
    parts.append('\n'.join(specs))
    parts.append("<!-- /SYSTEM:specs -->")
    parts.append("")

    # User: notes
    parts.append("<!-- USER:notes -->")
    notes = user_sections.get("notes", "").strip()
    if notes:
        parts.append(notes)
    parts.append("<!-- /USER:notes -->")

    # System: production
    if c.produced_at or c.consumed_at:
        parts.append("")
        parts.append("<!-- SYSTEM:production -->")
        prod_lines = ["===== Production ====="]
        if c.produced_at:
            prod_lines.append("==== Produced At ====")
            prod_lines.append("^ Location ^ Inputs ^ Time ^")
            for loc, inputs, time_s in c.produced_at:
                input_str = ', '.join(f"{qty}× {cid}" for cid, qty in inputs) if inputs else '(passive)'
                time_str = f"{time_s}s" if time_s else '—'
                prod_lines.append(f"| {loc} | {input_str} | {time_str} |")
        if c.consumed_at:
            prod_lines.append("==== Consumed At ====")
            prod_lines.append("^ Location ^ Time ^")
            for loc, _, time_s in c.consumed_at:
                time_str = f"{time_s}s" if time_s else '—'
                prod_lines.append(f"| {loc} | {time_str} |")
        parts.append('\n'.join(prod_lines))
        parts.append("<!-- /SYSTEM:production -->")

    result = '\n'.join(parts)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.rstrip() + '\n'


def sync_to_annie_wiki(
    conn: sqlite3.Connection,
    annie_wiki_db: str,
    dry_run: bool = False,
) -> dict:
    """Sync vehicle and cargo data to Annie's WikiStorage.

    Uses SYSTEM/USER section markers to preserve user-contributed content
    while regenerating system sections from game data.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'amc-peripheral'))

    from amc_peripheral.wiki.storage import WikiStorage
    from amc_peripheral.wiki.retrieval import WikiRetrieval

    storage = WikiStorage(db_path=annie_wiki_db)
    retrieval = None
    chromadb_path = str(Path(annie_wiki_db).parent / 'annie_wiki_chromadb')
    if Path(chromadb_path).exists():
        try:
            retrieval = WikiRetrieval(path=chromadb_path)
        except Exception as e:
            print(f"  Warning: ChromaDB not available for re-indexing: {e}")

    stats = {'created': 0, 'updated': 0, 'unchanged': 0, 'errors': 0}

    # Sync vehicles
    vehicles = load_vehicles(conn)
    for v in vehicles:
        slug = f"vehicle:{v.id}"
        existing = storage.get_page_by_slug(slug)

        user_sections = None
        if existing:
            user_sections = _extract_user_sections(existing.get('content', ''))

        new_content = _generate_annie_vehicle_content(v, user_sections)

        if existing:
            old_content = existing.get('content', '')
            if old_content == new_content:
                stats['unchanged'] += 1
                continue
            if not dry_run:
                storage.update_page(existing['id'], content=new_content)
                _reindex_page(storage, retrieval, existing['id'])
            stats['updated'] += 1
            action = "UPDATE"
        else:
            if not dry_run:
                page_id = storage.create_page(
                    title=slug,
                    category='vehicle',
                    content=new_content,
                    summary=f"{v.name} — {_fmt_type(v.vehicle_type)} vehicle",
                )
                storage.add_source(page_id, 'wiki_sync', f'motortown.db:{v.id}')
                _reindex_page(storage, retrieval, page_id)
            stats['created'] += 1
            action = "CREATE"

        print(f"  {action}: vehicle:{v.id}")

    # Sync cargos
    cargos = load_cargos(conn)
    for c in cargos:
        if c.is_deprecated:
            continue

        slug = f"cargo:{c.id}"
        existing = storage.get_page_by_slug(slug)

        user_sections = None
        if existing:
            user_sections = _extract_user_sections(existing.get('content', ''))

        new_content = _generate_annie_cargo_content(c, user_sections)

        if existing:
            old_content = existing.get('content', '')
            if old_content == new_content:
                stats['unchanged'] += 1
                continue
            if not dry_run:
                storage.update_page(existing['id'], content=new_content)
                _reindex_page(storage, retrieval, existing['id'])
            stats['updated'] += 1
            action = "UPDATE"
        else:
            if not dry_run:
                page_id = storage.create_page(
                    title=slug,
                    category='cargo',
                    content=new_content,
                    summary=f"{c.name} — {c.cargo_type} cargo",
                )
                storage.add_source(page_id, 'wiki_sync', f'motortown.db:{c.id}')
                _reindex_page(storage, retrieval, page_id)
            stats['created'] += 1
            action = "CREATE"

        print(f"  {action}: cargo:{c.id}")

    # Invalidate wiki index cache so LLM sees updated pages
    if not dry_run:
        storage.set_index_cache(None)

    storage.close()
    return stats


def _reindex_page(storage, retrieval, page_id: int):
    """Re-index a single page in ChromaDB after content update."""
    if retrieval is None:
        return
    try:
        page = storage.get_page_by_id(page_id)
        if page:
            retrieval.index_page(
                page_id=page_id,
                title=page['title'],
                content=page['content'],
                category=page['category'],
                updated_at=page['updated_at'],
            )
    except Exception as e:
        print(f"  Warning: ChromaDB re-index failed for page {page_id}: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Sync Motor Town game data to wiki targets')
    parser.add_argument('--db', required=True, help='Path to motortown.db')
    parser.add_argument('--wiki-dir', help='DokuWiki pages directory (required for dokuwiki target)')
    parser.add_argument('--target', choices=['dokuwiki', 'annie-wiki'], default='dokuwiki',
                        help='Sync target (default: dokuwiki)')
    parser.add_argument('--annie-wiki-db', help='Path to Annie wiki SQLite DB (required for annie-wiki target)')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without writing')
    parser.add_argument('--only', choices=['vehicles', 'cargos', 'indexes', 'parts'],
                        help='Only sync specific page type (dokuwiki target only)')
    parser.add_argument('--vehicle', help='Sync single vehicle by ID')
    parser.add_argument('--backup', action='store_true', help='Create backup before writing')

    args = parser.parse_args()

    db_path = Path(args.db)

    if not db_path.exists():
        print(f"Error: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))

    # --- Annie's Wiki target ---
    if args.target == 'annie-wiki':
        if not args.annie_wiki_db:
            print("Error: --annie-wiki-db is required for annie-wiki target", file=sys.stderr)
            sys.exit(1)
        annie_db = Path(args.annie_wiki_db)
        if not annie_db.exists():
            print(f"Error: Annie wiki database not found: {annie_db}", file=sys.stderr)
            sys.exit(1)

        mode = "DRY RUN" if args.dry_run else "LIVE"
        print(f"\n=== Annie Wiki Sync ({mode}) ===\n")
        stats = sync_to_annie_wiki(conn, str(annie_db), args.dry_run)
        print(f"\n  Total: {stats['created']} created, {stats['updated']} updated, "
              f"{stats['unchanged']} unchanged, {stats.get('errors', 0)} errors")
        conn.close()
        print("Done.")
        return

    # --- DokuWiki target (default) ---
    if not args.wiki_dir:
        print("Error: --wiki-dir is required for dokuwiki target", file=sys.stderr)
        sys.exit(1)

    wiki_dir = Path(args.wiki_dir)

    if not wiki_dir.exists():
        print(f"Error: Wiki directory not found: {wiki_dir}", file=sys.stderr)
        sys.exit(1)

    # Backup
    if args.backup and not args.dry_run:
        backup_name = f"wiki-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
        backup_path = wiki_dir.parent / backup_name
        print(f"Creating backup: {backup_path}")
        with tarfile.open(backup_path, 'w:gz') as tar:
            tar.add(wiki_dir, arcname='pages')
        print(f"Backup created: {backup_path}")

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"\n=== Wiki Sync ({mode}) ===\n")

    # Build slug map from existing wiki pages
    print("Building slug map from existing wiki pages...")
    slug_map, name_map = build_slug_map(wiki_dir)
    print(f"  Found {len(slug_map)} existing vehicle pages with Internal key mappings\n")

    # Load the part index (localized display names + install restrictions) so
    # vehicle pages can link parts, show Default Parts mass, and render the
    # Installable Parts aggregate section.
    global _PART_INDEX
    if not _PART_INDEX:
        _PART_INDEX = {p.id: p for p in load_parts(conn)}

    # Vehicles
    if args.only is None or args.only == 'vehicles':
        print("Syncing vehicles...")
        stats = sync_vehicles(conn, wiki_dir, slug_map, name_map, args.dry_run, args.vehicle)
        print(f"  Vehicles: {stats['created']} created, {stats['updated']} updated, "
              f"{stats['unchanged']} unchanged, {stats.get('errors', 0)} errors\n")

    # Cargos
    if args.only is None or args.only == 'cargos':
        print("Syncing cargos...")
        stats = sync_cargos(conn, wiki_dir, args.dry_run)
        print(f"  Cargos: {stats['created']} created, {stats['updated']} updated, "
              f"{stats['unchanged']} unchanged, {stats.get('errors', 0)} errors\n")

    # Parts
    if args.only is None or args.only == 'parts':
        print("Syncing parts...")
        stats = sync_parts(conn, wiki_dir, args.dry_run)
        print(f"  Parts: {stats['created']} created, {stats['updated']} updated, "
              f"{stats['unchanged']} unchanged, {stats.get('errors', 0)} errors\n")
        pstats = sync_parts_index(conn, wiki_dir, args.dry_run)
        print(f"  Parts Index: {pstats['created']} created, {pstats['updated']} updated, "
              f"{pstats['unchanged']} unchanged\n")

    # Indexes
    if args.only is None or args.only == 'indexes':
        print("Syncing indexes...")
        stats = sync_indexes(conn, wiki_dir, slug_map, name_map, args.dry_run)
        print(f"  Indexes: {stats['created']} created, {stats['updated']} updated, "
              f"{stats['unchanged']} unchanged\n")

    conn.close()
    print("Done.")


if __name__ == '__main__':
    main()
