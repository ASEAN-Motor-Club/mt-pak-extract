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
    # Raw gameplay-tag query string from the reference catalog (e.g.
    # 'NONE( Vehicle.EV )'). Evaluated against the vehicle's tags when set.
    tag_query: Optional[str] = None
    # tuning stats: {struct_type: {field: value}}
    stats: dict = field(default_factory=dict)
    # Reference-extractor name dict: {locale_tag: translated_name}. When present
    # (from ref_parts.json) it is authoritative over DB name/locres data.
    names: dict = field(default_factory=dict)


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
    # Gameplay tags from the reference vehicle catalog (for tag-query eval).
    ref_tags: list = field(default_factory=list)
    engine_id: str = ''
    # Engine info (parsed from part name)
    engine_hp: int = 0
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


def load_vehicles(conn: sqlite3.Connection, include_hidden: bool = False) -> list[Vehicle]:
    """Load vehicles from DB. Hidden vehicles are skipped unless include_hidden.

    The installable-parts sub-page should exist for every vehicle that has a
    wiki page, including hidden ones (trailers, karts, etc.), so sync uses
    include_hidden=True when generating those sub-pages.
    """
    cursor = conn.cursor()
    inner = conn.cursor()  # Separate cursor for sub-queries
    vehicles = []

    # Reference-extractor vehicle catalog (out_vehicle.json): authoritative
    # for English display names + vehicle type, so rows whose DB name is null
    # or a GUID fall back to the pak's real name instead of the internal id.
    _load_ref_data()

    hidden_clause = "WHERE 1=1" if include_hidden else "WHERE v.is_hidden = 0 OR v.is_hidden IS NULL"
    for row in cursor.execute(f"""
        SELECT v.id, v.name, v.vehicle_type, v.truck_class, v.cost, v.comport,
               v.is_hidden, v.is_disabled,
               COALESCE(vw.chassis_mass_kg, 0) as chassis_mass_kg,
               v.is_taxiable, v.is_limoable, v.is_busable, v.is_race_car,
               v.can_haul_trailer, v.has_fuel_pump,
               v.delivery_payment_multiplier, v.delivery_base_payment
        FROM vehicles v
        LEFT JOIN vehicle_weights vw ON v.id = vw.vehicle_id
        {hidden_clause}
        ORDER BY v.vehicle_type, v.name
""",):
        # Prefer the reference-extractor English name + type (pak) over the DB.
        _ref_v = _REF_VEHICLES.get(row[0], {})
        _ref_name = (_ref_v.get('name') or {}).get('en')
        _db_name = row[1]
        v = Vehicle(
            id=row[0],
            name=_ref_name or _db_name or row[0],
            vehicle_type=(_ref_v.get('type') or row[2] or '').rsplit('::', 1)[-1],
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

        # Overlay reference-extractor default parts when available: out_vehicle.json
        # gives the correct granular part key per slot (e.g. BasicTire_65 rather
        # than the DB's merged BasicTire). This fixes broken links and the DB's
        # duplicated-row bug. Only applied for vehicles matched by internal key.
        _load_ref_data()
        ref_vparts = _REF_VEHICLES.get(v.id, {}).get('parts')
        if ref_vparts:
            v.default_parts = list(ref_vparts.items())
        else:
            # Deduplicate the DB's doubled rows for non-matched vehicles.
            seen = set()
            dedup = []
            for slot, pid in v.default_parts:
                if (slot, pid) not in seen:
                    seen.add((slot, pid))
                    dedup.append((slot, pid))
            v.default_parts = dedup

        # Reference gameplay tags (used to evaluate parts' tag-query restrictions).
        ref_tags = _REF_VEHICLES.get(v.id, {}).get('tags') or []
        v.ref_tags = list(ref_tags)

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
    """Display name: real localized English name when the game has one, else the
    raw row key. NEVER invents/humanizes a name — parts without a locres entry
    are shown by their internal key (matching the reference extractor), because
    we cannot know what the game displays for them and must not fabricate it.
    """
    localized = _part_localized(locres_key)
    return localized if localized else part_id


# --- Reference extractor data (authoritative) ---
_REF_DIR = Path(__file__).resolve().parent.parent
_REF_PARTS: dict = {}     # part key -> {type,name,cost,massKg,restrict,stats}
_REF_VEHICLES: dict = {}  # vehicle key -> {name,type,...,parts:{slot:key}}

_ref_loaded = False


def _load_ref_data() -> None:
    """Load the reference extractor's ref_parts.json + out_vehicle.json once.

    When present, these are the authoritative source for part names (real,
    translated display names), costs, masses, per-part stats and vehicle
    default-part mappings. DB-derived names/locres are only a fallback.
    """
    global _ref_loaded, _REF_PARTS, _REF_VEHICLES
    if _ref_loaded:
        return
    _ref_loaded = True
    for fname, store in (("ref_parts.json", _REF_PARTS),
                         ("out_vehicle.json", _REF_VEHICLES)):
        store.clear()
        p = _REF_DIR / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  WARN: could not load {fname}: {e}")
            continue
        if fname == "ref_parts.json":
            store.update(data.get("parts", {}))
        else:
            store.update(data)


def _ref_part_names(part_key: str) -> dict:
    """The reference name dict {locale: name} for a part key, or {} if absent."""
    _load_ref_data()
    return _REF_PARTS.get(part_key, {}).get("name", {}) or {}


def _ref_part_en(part_key: str) -> Optional[str]:
    """Real English display name from the reference catalog, else None."""
    names = _ref_part_names(part_key)
    en = names.get("en")
    return en if en else None


def _part_ref_localized_langs(part_key: str) -> list[tuple[str, str]]:
    """[(language_label, name)] for all languages with a real translation,
    from the reference catalog. English first. Empty if the reference has no
    data for this part.
    """
    names = _ref_part_names(part_key)
    if not names:
        return []
    en = names.get("en")
    if not en:
        return []
    out = [("English", en)]
    for tag in _LOCALE_ORDER:
        if tag == "en":
            continue
        v = names.get(tag)
        if v and v != en:
            out.append((_LOCALE_NAME.get(tag, tag), v))
    return out


def _json_load(s) -> list:
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def load_parts(conn: sqlite3.Connection) -> list[Part]:
    """Load all vehicle parts.

    When the reference extractor catalog (ref_parts.json) is present it is the
    authoritative source: it carries the game's real display names (per
    language), true costs/masses, resolved per-part stats and vehicle
    restriction data. DB-derived parts are only used as a fallback for any key
    the reference does not cover, so vehicle pages can still resolve links.

    Also populates the module-global _PART_INDEX (part_id -> Part).
    """
    global _PART_INDEX
    _load_ref_data()
    parts: list[Part] = []

    if _REF_PARTS:
        for pid, rd in _REF_PARTS.items():
            names = rd.get('name') or {}
            restrict = rd.get('restrict') or {}
            vehicle_types = [
                t.split('::')[-1] for t in (restrict.get('types') or [])
            ]
            truck_classes = [
                t.split('::')[-1] for t in (restrict.get('truckClasses') or [])
            ]
            p = Part(
                id=pid,
                name=names.get('en') or pid,
                part_type=rd.get('type') or '',
                cost=rd.get('cost') or 0,
                mass_kg=rd.get('massKg') or 0.0,
                is_hidden=False,
                names=names,
                vehicle_types=vehicle_types,
                truck_classes=truck_classes,
                truck_class_include_none=bool(restrict.get('truckClassIncludeNone')),
                vehicle_keys=[k for k in (restrict.get('keys') or []) if k != 'None'],
                override_vehicle_keys=restrict.get('overrideKeys') or [],
                slots=restrict.get('slots') or [],
                tag_query=restrict.get('tagQuery'),
            )
            p.stats = rd.get('stats') or {}
            parts.append(p)
        by_id = {p.id: p for p in parts}
        _PART_INDEX = by_id
        return parts

    # --- Fallback: DB-driven parts (no reference catalog present) ---
    cursor = conn.cursor()
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


_INFOBOX_GEN_KEYS = {'name', 'internal key', 'type', 'cost', 'weight', 'engine',
                     'drivetrain', 'cargo space', 'drag coefficient'}


def generate_vehicle_infobox(v: Vehicle, existing_image: Optional[str] = None,
                             existing_infobox: Optional[str] = None) -> str:
    """Generate the infobox section for a vehicle.

    Auto-generates the known/verifiable fields (name, key, type, cost, weight,
    engine, drivetrain, cargo space, drag). Any *other* lines present in the
    existing infobox (user-curated Comfort, Fuel, Seats, Level requirement,
    Axle lift, etc.) are preserved, so a regeneration doesn't drop them.
    """
    generated: list[str] = []
    emitted = set()

    def add(key: str, val: str):
        generated.append(f"{key} = {val}")
        emitted.add(key.lower())

    add('name', v.name)
    add('Internal key', v.id)

    vtype = _fmt_type(v.vehicle_type)
    tclass = _fmt_type(v.truck_class)
    type_str = f"{vtype}, {tclass}" if tclass else vtype
    add('Type', type_str)
    add('Cost', _fmt_cost(v.cost))
    add('Weight', _fmt_weight(v.chassis_mass_kg))

    if v.engine_hp:
        add('Engine', f"{v.engine_hp} HP")

    drivetrain = _get_drivetrain(v.default_parts)
    if drivetrain:
        add('Drivetrain', drivetrain)

    if v.cargo_space_type:
        add('Cargo space', v.cargo_space_type)

    add('Drag coefficient', f"{v.air_drag}")

    # Preserve user-curated lines from the existing infobox that we do not
    # regenerate (Comfort, Fuel, Seats, Level requirement, Axle lift, ...).
    preserved = []
    if existing_infobox:
        for line in existing_infobox.split('\n'):
            stripped = line.strip()
            if '=' not in stripped:
                continue
            key, _, val = stripped.partition('=')
            canon = key.strip().lower()
            if canon in _INFOBOX_GEN_KEYS or canon in emitted:
                continue
            preserved.append(f"{key.strip()} = {val.strip()}")
            emitted.add(canon)

    lines = ["{{infobox>"]
    if existing_image:
        lines.append(existing_image)  # image = ... replaces name line
        lines.extend(generated[1:])
    else:
        lines.extend(generated)
    if preserved:
        lines.append("")
        lines.extend(preserved)
    lines.append("}}")
    return '\n'.join(lines)


def generate_vehicle_heading(v: Vehicle) -> str:
    """Generate vehicle page heading."""
    vtype = _fmt_type(v.vehicle_type).lower()
    tclass = _fmt_type(v.truck_class).lower()
    type_desc = f"{tclass} {vtype}" if tclass else vtype

    return f"====== {v.name} ======\n**{v.name}** is a {type_desc} vehicle in [[:motor_town|Motor Town]]"


def generate_vehicle_specs(v: Vehicle, slug: str = '') -> str:
    """Generate the specifications section.

    slug: the vehicle's wiki page slug. When provided, an "Installable Parts"
    section links to the per-vehicle sub-page (Wikipedia style — the main page
    holds only the link, the full list lives on `vehicles:<slug>:installable_parts`).
    """
    lines = ["===== Specifications ====="]

    # Key stats table
    lines.append("^ Stat ^ Value ^")

    # Engine
    if v.engine_id:
        hp_str = f" ({v.engine_hp} HP)" if v.engine_hp else ""
        ep = _PART_INDEX.get(v.engine_id)
        edisp = ep.name if ep else v.engine_id
        lines.append(f"| Engine | [[parts:{_part_slug(v.engine_id)}|{edisp}]]{hp_str} |")

    # Transmission
    transmission = next((pid for slot, pid in v.default_parts if slot == 'Transmission'), None)
    if transmission:
        tp = _PART_INDEX.get(transmission)
        tdisp = tp.name if tp else transmission
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

    # Default Parts table. Mass shown is the TOTAL fitted on the vehicle
    # (per-part mass × how many copies of that part the vehicle carries), e.g.
    # 4 tires at 80 kg each display as "320 kg".
    grouped = _group_parts(v.default_parts)
    if grouped:
        lines.append("")
        lines.append("===== Default Parts =====")
        lines.append("^ Slot ^ Part ^ Total Mass ^")
        for base, part_id, count in grouped:
            count_str = f" (×{count})" if count > 1 else ""
            pp = _PART_INDEX.get(part_id)
            disp = _part_display_name(pp) if pp else part_id
            if pp and pp.mass_kg:
                mass = _fmt_weight(pp.mass_kg * count)
            else:
                mass = "—"
            lines.append(f"| {base} | [[parts:{_part_slug(part_id)}|{disp}]]{count_str} | {mass} |")

    # Installable Parts — Wikipedia style: the main page holds only a link to
    # the per-vehicle sub-page which lists every compatible part grouped by
    # type. Requires the slug to build the link; without it (e.g. a bare
    # spec-only render) we emit a plain heading.
    if slug:
        lines.append("")
        lines.append("===== Installable Parts =====")
        lines.append("")
        lines.append(f"See [[vehicles:{slug}:installable_parts|Installable parts for {v.name}]].")
    else:
        lines.append("")
        lines.append("===== Installable Parts =====")

    return '\n'.join(lines)


def _eval_tag_query(query: str, veh_tags: list[str]) -> bool:
    """Evaluate a gameplay-tag query expression against a vehicle's tags.

    The query language (from the reference extractor) is a small lisp-like
    tree: ALL(...), ANY(...), NONE(...) with tag operands (e.g. 'Vehicle.EV',
    'Vehicle.Key.Atlas', 'VehiclePart.VehicleKeySpecific.AtlasRoof1') and
    nested expressions. An ALL with a single operand is the common case.
    """
    q = (query or '').strip()
    if not q:
        return True

    def _has(tag: str) -> bool:
        tag = tag.strip()
        return tag in veh_tags or tag == 'Vehicle.Key.' or tag == 'Vehicle'

    def _eval(expr: str) -> bool:
        expr = expr.strip()
        if not expr:
            return True
        # Empty ALL/NONE/ANY collapsed to just the inner expr.
        if expr.startswith('ALL('):
            inner = expr[4:].rstrip(')').strip()
            parts = _split_args(inner)
            if not parts:
                return True
            return all(_eval(p) for p in parts if p.strip())
        if expr.startswith('ANY('):
            inner = expr[4:].rstrip(')').strip()
            parts = _split_args(inner)
            if not parts:
                return True
            return any(_eval(p) for p in parts if p.strip())
        if expr.startswith('NONE('):
            inner = expr[5:].rstrip(')').strip()
            return not _eval(inner)
        return _has(expr)

    return _eval(q)


def _split_args(s: str) -> list[str]:
    """Split a comma-separated arg list, respecting nested parentheses."""
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == '(':
            depth += 1
            cur.append(ch)
        elif ch == ')':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur))
    return parts


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
    # Gameplay tag query: empty = no filter; else the vehicle's tags must satisfy it.
    if p.tag_query:
        if not _eval_tag_query(p.tag_query, list(getattr(v, 'ref_tags', None) or [])):
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
        result[tn].sort(key=_natural_part_key)
    return result


def generate_installable_parts_page(v: Vehicle, slug: str = '') -> str:
    """Generate the per-vehicle "Installable Parts" sub-page.

    This is a full standalone page at `vehicles:<slug>:installable_parts`
    listing every part compatible with vehicle v, grouped by part type, with a
    link back to the parent vehicle page (Wikipedia style).
    """
    installable = _installable_for_vehicle(v)
    total = sum(len(x) for x in installable.values())

    lines = [
        f"====== Installable Parts for {v.name} ======",
        "",
        f"All vehicle parts that can be installed on the **{v.name}** "
        f"({len(installable)} part types, {total} parts in total).",
        "",
        f"Return to [[vehicles:{slug}|{v.name}]].",
        "",
    ]

    for type_name in sorted(installable.keys()):
        plist = installable[type_name]
        lines.append(f"===== {type_name} ({len(plist)}) =====")
        lines.append("")
        lines.append("^ Part ^ Cost ^ Mass ^")
        for pp in plist:
            mass = _fmt_weight(pp.mass_kg) if pp.mass_kg else '—'
            lines.append(f"| [[parts:{_part_slug(pp.id)}|{_part_display_name(pp)}]] | {_fmt_cost(pp.cost)} | {mass} |")
        lines.append("")

    if not installable:
        lines.append("No installable parts found for this vehicle.")
        lines.append("")

    # User placeholder consistent with other pages
    lines.append("===== Notes =====")
    lines.append("")

    return '\n'.join(lines).rstrip() + '\n'


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


# Vehicle type enum tails -> user-facing grouping label. Mirrors how the
# curated list_(of)_vehicles splits camel-cased enum tails into words (e.g.
# 'SemiTrailer' -> 'Semi Trailer', 'SemiTractor' -> 'Semi Tractor').
_VEHICLE_TYPE_LABEL = {
    'SemiTrailer': 'Semi Trailer',
    'SemiTractor': 'Semi Tractor',
    'Kart': 'Kart',
    'Small': 'Small',
    'Truck': 'Truck',
    'Bus': 'Bus',
}


def _humanize_vehicle_type(vtype: str) -> str:
    """User-facing vehicle-type group label for list/comparison tables."""
    if not vtype:
        return 'Other'
    if vtype in _VEHICLE_TYPE_LABEL:
        return _VEHICLE_TYPE_LABEL[vtype]
    if vtype in ('SemiTrailer', 'SemiTractor'):
        return 'Semi Trailer' if vtype == 'SemiTrailer' else 'Semi Tractor'
    # Split remaining camel/underscore tails into words.
    s = vtype.replace('_', ' ')
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', s)
    return s or 'Other'


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


def _display_name_key(name: str):
    """Natural sort key for a DISPLAYED part name.

    - Pure numeric names (including a trailing unit like %, cm, km): compared
      numerically (`50%` < `120%`, `1.33` < `1.8` < `14`).
    - Otherwise: split into text / digit runs, comparing text runs
      case-insensitively and digit runs numerically (`F50` < `F60` < `F110`,
      `KM1-65` < `KM2-45`, `#1 (Koma)` < `#2 (Zydro)`).
    """
    name = (name or '').strip()

    def _num_tokens(s):
        return re.findall(r'\d+(?:\.\d+)?|.', s)

    # Pure numeric with optional trailing unit/sign -> (0, float, unit-lower)
    m = re.fullmatch(r'([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z%°\u00b2\u00b3]*)', name)
    if m:
        try:
            return (0, float(m.group(1)), m.group(2).lower())
        except ValueError:
            pass

    # Split into alternating text/digit runs.
    tokens = re.findall(r'\d+(?:\.\d+)?|[^0-9]+', name)
    key = []
    for t in tokens:
        if re.fullmatch(r'\d+(?:\.\d+)?', t):
            key.append((0, float(t)))          # (kind=number, value)
        else:
            key.append((1, t.lower()))          # (kind=text, lowercase text)
    return (1, key, name.lower())


def _natural_part_key(obj):
    """Sort key for a part (by displayed name, numeric-aware)."""
    if hasattr(obj, 'id'):
        return _display_name_key(_part_display_name(obj))
    return _display_name_key(obj)


def generate_part_page(p: Part) -> str:
    """Generate a full part wiki page."""
    parts = []
    dname = _part_display_name(p)

    # Infobox
    infobox = [
        "{{infobox>",
        f"name = {dname}",
        f"Part Type = {_part_type_name(p.part_type)}",
        f"Cost = {_fmt_cost(p.cost)}",
    ]
    if p.mass_kg:
        infobox.append(f"Mass = {_fmt_weight(p.mass_kg)}")
    infobox.append("}}")
    parts.append('\n'.join(infobox))
    parts.append("")

    # Heading
    parts.append(f"====== {dname} ======")
    parts.append("")
    type_lower = _part_type_name(p.part_type).lower()
    article = 'an' if type_lower[:1] in ('a', 'e', 'i', 'o', 'u') else 'a'
    parts.append(f"**{dname}** is {article} {type_lower} part for vehicles in [[:motor_town|Motor Town]].")
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

    # Stats (tuning values from the reference catalog)
    if p.stats:
        parts.append(_render_part_stats(p))
        parts.append("")

    # In other languages — at the bottom of the page.
    i18n_lines = ["===== In other languages =====", "^ Language ^ Name ^"]
    i18n_rows = _part_ref_localized_langs(p.id)
    if i18n_rows:
        for label, name in i18n_rows:
            i18n_lines.append(f"| {label} | {name} |")
    else:
        i18n_lines.append(f"| English | {p.name} |")
        i18n_lines.append("| _(no other translations available)_ | _— n/a_ |")
    parts.append('\n'.join(i18n_lines))

    return '\n'.join(parts) + '\n'


def _display_field(field: str) -> str:
    """Humanize a stat field name: 'MaxTorque' -> 'Max Torque'."""
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', field).replace('_', ' ').strip() or field


# ---------------------------------------------------------------------------
# Reader-friendly stat rendering
#
# The stats come from the reference catalog as nested dicts. We render them as
# "Stat | Value" DokuWiki rows (consistent with Specifications), turning raw
# JSON/asset drops into human-friendly text. Per-field metadata gives a stable
# display label + unit; anything not in the table falls back to a humanized
# field name with no unit (rather than guessing).
#
# Junk fields (mesh/sound/anim asset refs, attach plumbing) are omitted
# outright — they add no tuning information.
# ---------------------------------------------------------------------------

# (field) -> (label, unit). Fields not listed: label = humanized name, no unit.
#
# unit kinds:
#   ''              plain number (no unit)
#   '%'             ABSOLUTE percentage  -> value * 100 %   (1.0 = the whole)
#   '±'             MULTIPLIER from 100  -> (value-1)*100 % (1.0 = stock)
#   'cur'           a value followed by % when it is a stock multiplier of 1.0
#   'G'             tire grip coefficient (mu), relabelled as G, never %
#   <literals>      value + " " + unit (rpm, s, kg, cm, mm, L, °C, ...)
#   'vec'/'vecmm'   XYZ dict -> "X cm × Y cm × Z cm"
#
# Aero fields are treated separately by the renderer; only the drag fields that
# live on the Tire/structural rows are listed here.
_STAT_LABEL_UNIT = {
    # Engine
    'MaxRPM': ('Max RPM', 'rpm'),
    'MaxTorque': ('Max Torque', 'N·m'),
    'StarterTorque': ('Starter Torque', 'N·m'),
    'Inertia': ('Rotational Inertia', 'kg·m²'),
    'FrictionViscosityCoeff': ('Friction Viscosity', ''),
    'FrictionCoulombCoeff': ('Friction Coulomb Coefficient', ''),
    'IdleThrottle': ('Idle Throttle', '%'),
    'BlipThrottle': ('Blip Throttle', ''),
    'AfterFireProbability': ('After-Fire Probability', '%'),
    'CoolingEfficiency': ('Cooling Efficiency', '±'),
    'HeatingPower': ('Heating Power', '±'),
    'IntakeSpeedEfficencyMultiplier': ('Intake Speed Efficiency', '±'),
    'BlipDurationSeconds': ('Blip Duration', 's'),
    'FuelConsumption': ('Fuel Consumption', ''),
    'FuelType': ('Fuel Type', ''),
    'EngineType': ('Engine Type', ''),
    'MaxJakeBrakeStep': ('Max Jake Brake Step', ''),
    'StarterRPM': ('Starter RPM', 'rpm'),
    'MaxRegenTorqueRatio': ('Max Regen Torque Ratio', '%'),
    'MotorMaxPower': ('Motor Max Power', 'W'),
    'MotorMaxVoltage': ('Motor Max Voltage', 'V'),
    # Transmission
    'TorqueConvertorStallRPM': ('Torque Converter Stall RPM', 'rpm'),
    'TorqueConvertorStallRatioPower': ('Torque Converter Stall Ratio Power', ''),
    'DefaultGearIndex': ('Default Gear', ''),
    'ShiftTimeSeconds': ('Shift Time', 's'),
    'TorqueConvertorTorqueRate': ('Torque Converter Torque Rate', ''),
    'ClutchType': ('Clutch Type', ''),
    'AutoShiftComportRPM': ('Comfort Autoshift RPM', 'rpm'),
    'DevComment': ('Inspiration', ''),
    'CVT_InputRPMRange': ('CVT Input RPM Range', 'rm'),
    'CVT_GearRatios': ('CVT Gear Ratios', 'rm'),
    'CVT_ClutchCurvePow': ('CVT Clutch Curve Power', ''),
    # Tire physics
    'SlidingMu': ('Sliding Grip', 'G'),
    'StaticMu': ('Static Grip', 'G'),
    'OffroadFriction': ('Offroad Grip', '±'),
    'SpringX': ('Spring Rate X', 'N/m'),
    'SpringY': ('Spring Rate Y', 'N/m'),
    'DampingX': ('Damping X', 'N·s/m'),
    'DampingY': ('Damping Y', 'N·s/m'),
    'WearRate': ('Wear Rate', '%'),
    'RollingResistanceCoeff': ('Rolling Resistance Coefficient', ''),
    'CoolDownSpeed': ('Cool Down Speed', ''),
    'WarmUpSpeed': ('Warm Up Speed', ''),
    'SmokeRate': ('Smoke Rate', ''),
    'bIsDualRearWheel': ('Dual Rear', ''),
    'MaxWeightKg': ('Max Load', 'kg'),
    'PatchLengthCoefficient': ('Patch Length Coefficient', ''),
    # Suspension
    'RideHeightChange': ('Ride Height Change', 'cm'),
    'BoundDampingRateMultiplier': ('Bound Damping Rate', '±'),
    'ReboundDampingRateMultiplier': ('Rebound Damping Rate', '±'),
    'SpringRateMultiplier': ('Spring Rate', '±'),
    'AntiRollBarRateMultiplier': ('Anti-Roll Bar Rate', '±'),
    # Brakes
    'FrontMultiplier': ('Front Brake Bias', '±'),
    'RearMultiplier': ('Rear Brake Bias', '±'),
    'BrakePowerMultiplier': ('Brake Power', '±'),
    'FadeTemperature': ('Fade Temperature', '°C'),
    'CoolingMultiplier': ('Brake Cooling', '±'),
    'HeatingMultiplier': ('Heating', '±'),
    'WearMultiplier': ('Wear Rate', '±'),
    # Coolant
    'CoolingPower': ('Cooling Power', '±'),
    'CoolantWaterInLiter': ('Coolant Capacity', 'L'),
    # Intake / Turbo
    'Slope': ('Intake Torque Slope', ''),
    'BaseRPMRatio': ('Base RPM Ratio', ''),
    'BaseTorqueMultiplier': ('Base Torque', '±'),
    'TorqueMultiplier': ('Torque', '±'),
    'TurbineAspectRatio': ('Turbine Aspect Ratio', ''),
    'IntakePressureMultiplier': ('Intake Pressure', '±'),
    'FuelConsumptionMultiplier': ('Fuel Consumption', '±'),
    'TurbineWeight': ('Turbine Weight', 'kg'),
    # Wheels / spacers
    'Space': ('Width', 'mm'),
    'NumSlots': ('Slots', ''),
    # Fuel / cargo
    'FuelLiter': ('Fuel Capacity', 'L'),
    'DumpVolume': ('Dump Volume', 'kL'),
    'CargoSpaceLocation': ('Cargo Space Location', 'vec'),
    'CargoSpaceSize': ('Cargo Space Size', 'vec'),
    'CargoSpaceType': ('Cargo Space Type', ''),
    # Misc tuning
    'AngleIncreaseInDegree': ('Angle Increase', 'deg'),
    'MaxForceKg': ('Max Force', 'kg'),
    'MaxLength': ('Cable Length', 'm'),
    'LSDType': ('LSD Type', ''),
    'ClutchPackAccel': ('Clutch Pack Acceleration', ''),
    'ClutchPackBrake': ('Clutch Pack Brake', ''),
    'TaxiType': ('Type', ''),
    'ConnectionType': ('Connection', ''),
    # Scalar stats structs where the field name IS the value (fallback label)
    'Winch': ('Winch', ''),
    'ItemInventory': ('Slots', ''),
    'CoolantRadiator': ('Coolant', ''),
    'BrakePad': ('Fade Temperature', '°C'),
    'CargoBed': ('Cargo Space', ''),
}

# Extra unit multipliers for fields whose raw unit differs from the display
# unit (e.g. Space is stored in cm but displayed in mm; winch length cm->m).
_STAT_MULT = {
    'Space': 10,
    'MaxLength': 0.01,
}

# Whole-vehicle aero fields: (label, force-multiplier-in-kg-per-coef at 200km/h)
_AERO_LIFT_FIELDS = {
    'AeroLift': ('Aero Lift', 1),
    'FrontAeroLift': ('Front Aero Lift', 0.5),
    'RearAeroLift': ('Rear Aero Lift', 0.5),
}

_AERO_DRAG_FIELDS = {
    'AirDragMultiplier': 'Air Drag',
    'TrailerAirDragMultiplier': 'Trailer Air Drag',
    'FrontDamageMultiplier': 'Front Damage',
}

# Stat "struct" keys that are pure asset/attach plumbing — omit entirely.
_STAT_DROP_STRUCTS = {'Aero'}

# Field names that are asset/mesh/sound references and add no tuning info.
_STAT_DROP_FIELDS = {
    'Mesh', 'LeftWheelMesh', 'RightWheelMesh', 'DRWLeftWheelMesh',
    'DRWRightWheelMesh', 'RearLeftWheelMesh', 'RearRightWheelMesh',
    'QuadWheelMesh', 'TirePhysicsDataAsset', 'TirePhysicsDataAsset_BikeRear',
    'LightOnAnim', 'BodyMesh', 'AxleMesh', 'HookMesh', 'StartSound',
    'ReleaseSound', 'MotorInSound', 'MotorOutSound', 'RopeCrackingSound',
    'RopeSnapSound', 'TaxiRoofSignClass', 'AttachParentComponentName',
    'ComponentTags', 'CustomSocketName', 'bUseCustomSocket', 'SkelealMesh',
    'bIsValid', 'bFixCargo', 'bUnlimitedHeight',
    'TirePhysicsDataAsset',
}

# Enum fields whose tail should be humanized for display (e.g.
# 'EMTLSDType::ClutchPackLSD' -> 'Clutch Pack LSD'). Includes booleans that
# read as "Yes/No" via _fmt_simple_value.
_STAT_BOOL_FIELDS = {'LSDType', 'TaxiType', 'ConnectionType', 'CargoSpaceType'}

# Enum field -> humanized tail mapping. Falls back to camel-case splitting
# (e.g. 'MultiPlateClutch' -> 'Multi Plate Clutch'), then the raw tail.
_ENUM_HUMANIZE_OVERRIDE = {
    'EMTLSDType::ClutchPackLSD': 'Clutch Pack LSD',
    'EMTLSDType::Lockable': 'Lockable',
    'EMTLSDType::LimitedSlip': 'Limited Slip',
    'EMTTaxiType::Normal': 'Normal',
    'EMTTaxiType::Limo': 'Limo',
    'EMTTrailerConnectionType::Hitch': 'Hitch',
    'EMTTrailerConnectionType::Ring': 'Ring',
    'EMTCargoSpaceType::Flatbed': 'Flatbed',
    'EMTCargoSpaceType::Box': 'Box',
    'EMTCargoSpaceType::Tanker': 'Tanker',
    'EMTTransmissionClutchType::MultiPlateClutch': 'Multi Plate Clutch',
    'EMTTransmissionType::EatonFuller13': 'Eaton Fuller 13',
    'EMTTransmissionType::EatonFuller18': 'Eaton Fuller 18',
    'EMTTransmissionType::CVT': 'CVT',
    'EMTFuelType::Diesel': 'Diesel',
    'EMTFuelType::Petrol': 'Petrol',
    'EMTFuelType::Electric': 'Electric',
    'EMTEngineType::Large': 'Large',
    'EMTEngineType::Medium': 'Medium',
    'EMTEngineType::Small': 'Small',
    'EMTEngineType::Bike': 'Bike',
    'EMTEngineType::Moped': 'Moped',
    'EMTEngineType::Scooter': 'Scooter',
    'EMTEngineType::EV': 'EV',
}


def _trim_number(v) -> str:
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return f"{v:.2f}".rstrip('0').rstrip('.')
    return str(v)


def _fmt_vec(value) -> str:
    """Reader-friendly vector: {'X':..,'Y':..,'Z':..} -> 'x, y, z'."""
    if not isinstance(value, dict):
        return _display_value(value)
    x = value.get('X', 0)
    y = value.get('Y', 0)
    z = value.get('Z', 0)
    return f"{_trim_number(x)}, {_trim_number(y)}, {_trim_number(z)}"


def _fmt_vec_dims(value) -> str:
    """Cargo-space vector: {'X':..,'Y':..,'Z':..} -> 'X cm × Y cm × Z cm'."""
    if not isinstance(value, dict):
        return _display_value(value)
    x = value.get('X', 0)
    y = value.get('Y', 0)
    z = value.get('Z', 0)
    def _d(v):
        if isinstance(v, (int, float)) and abs(v) < 0.5:
            return '0'
        return _trim_number(v)
    return f"{_d(x)} cm × {_d(y)} cm × {_d(z)} cm"


def _fmt_rng(value, unit: str = '') -> str:
    """CVT range {'X':..,'Y':..} -> '1000 – 7000 rpm'."""
    if not isinstance(value, dict):
        return _display_value(value)
    x = value.get('X', 0)
    y = value.get('Y', 0)
    s = f"{_trim_number(x)} – {_trim_number(y)}"
    return f"{s} {unit}".strip() if unit else s


def _fmt_number(value) -> str:
    """Number with thousands separators for large engine/torque magnitudes."""
    if isinstance(value, float) and value == int(value):
        value = int(value)
    if isinstance(value, int) and abs(value) >= 10000:
        return f"{value:,}"
    return _trim_number(value)


def _fmt_delta_from_100(value) -> str:
    """Multiplier from 100: (value-1)*100%, signed. 1.0 -> ±0%."""
    d = (value - 1.0) * 100
    if abs(d) < 1e-9:
        return "±0%"
    return _fmt_signed(d) + '%'


def _humanize_enum(value: str) -> str:
    """'EMTxxx::ClutchPackLSD' -> 'Clutch Pack LSD' (override) / camel split."""
    key = value
    if '::' in value:
        key = value.rsplit('::', 1)[-1]
    if value in _ENUM_HUMANIZE_OVERRIDE:
        return _ENUM_HUMANIZE_OVERRIDE[value]
    # camel-case split fallback: 'MultiPlateClutch' -> 'Multi Plate Clutch'
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', key)
    return s or key


def _fmt_simple_value(value, unit: str = '') -> str:
    """Format a scalar stat value.

    Units: '' = none; '%' = absolute ×100; '±' = multiplier ±% from 100;
    'G' = grip coefficient (relabelled, never %); ''/literal = number + unit
    with thousands separators for large engine/torque magnitudes.
    """
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, float)):
        if unit == '%':
            return f"{_trim_number(value * 100)}%"
        if unit == '±':
            return _fmt_delta_from_100(value)
        if unit == 'G':
            return f"{_trim_number(value)} G"
        if unit in ('N·m', 'W', 'V'):
            return f"{_fmt_number(value)} {unit}".strip()
        s = _trim_number(value)
        return f"{s} {unit}".strip() if unit else s
    return str(value)


def _display_value(value) -> str:
    """Format a stat value for the wiki without raw JSON drops."""
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.2f}".rstrip('0').rstrip('.')
    if isinstance(value, dict):
        # Object refs / asset paths -> short name only.
        obj = value.get('ObjectName') or value.get('AssetPathName')
        if obj:
            return str(obj)
        # Vector
        if 'X' in value and 'Y' in value and 'Z' in value:
            return _fmt_vec(value)
        # Single-key asset path
        return json.dumps(value)
    if isinstance(value, list):
        return _fmt_list(value)
    return str(value)


def _fmt_list(value) -> str:
    """Reader-friendly list rendering (avoid JSON drops)."""
    out = []
    for item in value:
        if isinstance(item, dict):
            # Torque curve point {Time, Value} / gear {Name, GearRatio, Inertia}
            if 'Value' in item and 'Time' in item:
                out.append(f"{_fmt_simple_value(item['Value'])} @ {_trim_number(item['Time'])}")
            elif 'Name' in item and 'GearRatio' in item:
                out.append(f"{item['Name']}:{_trim_number(item['GearRatio'])}")
            else:
                out.append(_display_value(item))
        elif isinstance(item, (dict, list)):
            out.append(_display_value(item))
        else:
            out.append(_display_value(item))
    if not out:
        return '—'
    return ', '.join(out)


_STAT_STRUCT_NAME = {
    'engine': 'Engine Physics', 'tire': 'Tire Physics', 'lsd': 'LSD',
    'transmission': 'Transmission Physics', 'Aero': 'Aero',
    'AngleKit': 'Angle Kit', 'AntiRollBar': 'Anti-Roll Bar',
    'BrakeBalance': 'Brake Balance', 'BrakePad': 'Brake Pad',
    'BrakePower': 'Brake Power', 'CargoBed': 'Cargo Bed',
    'CoolantRadiator': 'Coolant Radiator', 'FinalDriveRatio': 'Final Drive Ratio',
    'FuelTank': 'Fuel Tank', 'Headlight': 'Headlight', 'Intake': 'Intake',
    'ItemInventory': 'Inventory', 'RoofRack': 'Roof Rack',
    'SuspensionDamper': 'Suspension Damper',
    'SuspensionRideHeight': 'Suspension Ride Height',
    'SuspensionSpring': 'Suspension Spring', 'Taxi': 'Taxi', 'Tire': 'Tire',
    'TrailerHitch': 'Trailer Hitch', 'Turbocharger': 'Turbocharger',
    'Wheel': 'Wheel', 'WheelSpacer': 'Wheel Spacer', 'Winch': 'Winch',
    'Utility': 'Utility', 'Headlight': 'Headlight',
}


def _stat_struct_name(struct: str) -> str:
    """Human-readable name for a stats struct key from the reference catalog."""
    if struct in _STAT_STRUCT_NAME:
        return _STAT_STRUCT_NAME[struct]
    return _display_field(struct) or struct


def _part_display_name(p: Part) -> str:
    """Display name for a part.

    Numbered parts (display name is a bare number like '#1') that are
    restricted to one or more specific vehicles get that vehicle's name(s)
    appended in parentheses: '#1 (Vista)' or '#2 (Koma #1 via link)'.
    Multi-vehicle restrictions join the names: '#1 (Nuke / Nuke Taxi)'.
    """
    _load_ref_data()
    keys = [k for k in (p.vehicle_keys or []) if k]
    if keys:
        name = p.name or ''
        if re.fullmatch(r'#?\d+', name):
            names = []
            for k in keys:
                veh = _REF_VEHICLES.get(k, {}).get('name', {}).get('en')
                names.append(veh or k)
            return f"{name} ({' / '.join(names)})"
    return p.name or p.id


_TYPE_SCHEMA_CACHE: dict = {}


def _norm_val(v):
    """Normalize a value for default comparison."""
    if isinstance(v, float) and v == int(v):
        return int(v)
    if isinstance(v, dict):
        return json.dumps(v, sort_keys=True)
    if isinstance(v, list):
        return json.dumps(v)
    return v


def _build_type_schema(part_type: str) -> list:
    """Build the stat schema for a part type.

    Returns an ordered list of dict-struct groups. Each group is
    ``(struct_key, display_name, [(field, label, unit, default)])`` where
    ``default`` is the mode (most common) value for that (struct, field)
    across all parts of the type. Aero scalar fields are grouped separately
    by the renderer, so they are omitted here.
    """
    if part_type in _TYPE_SCHEMA_CACHE:
        return _TYPE_SCHEMA_CACHE[part_type]
    _load_ref_data()

    # Collect every (struct, field) -> list of the values seen for parts of
    # this type, preserving field encounter order per struct. Also count how
    # many parts actually carry each field, so "present on some only" fields
    # (e.g. engine CoolingEfficiency/StarterRPM) can be omitted when a given
    # part lacks them rather than shown with a fabricated default.
    struct_values: dict[str, dict[str, list]] = {}
    struct_counts: dict[str, dict[str, int]] = {}
    struct_order: list[str] = []
    total_parts = 0
    for rd in _REF_PARTS.values():
        if rd.get('type') != part_type:
            continue
        total_parts += 1
        for st, sval in (rd.get('stats') or {}).items():
            if st in _STAT_DROP_STRUCTS or st in _AERO_LIFT_FIELDS or st in _AERO_DRAG_FIELDS:
                continue  # aero/drop handled elsewhere
            if not isinstance(sval, dict):
                # Scalar non-aero struct (e.g. FinalDriveRatio) handled as a row.
                if st not in struct_order:
                    struct_order.append(st)
                struct_values.setdefault(st, {}).setdefault('__scalar__', []).append(sval)
                struct_counts.setdefault(st, {})['__scalar__'] = struct_counts.setdefault(st, {}).get('__scalar__', 0) + 1
                continue
            if st not in struct_order:
                struct_order.append(st)
            sv = struct_values.setdefault(st, {})
            sc = struct_counts.setdefault(st, {})
            for f, v in sval.items():
                if f in _STAT_DROP_FIELDS:
                    continue
                sv.setdefault(f, []).append(v)
                sc[f] = sc.get(f, 0) + 1

    schema = []
    for st in struct_order:
        fields = []
        sv = struct_values[st]
        sc = struct_counts[st]
        if '__scalar__' in sv:
            vals = sv['__scalar__']
            default = _mode(vals)
            present_all = sc.get('__scalar__', 0) >= total_parts
            fields.append(('__scalar__', _stat_struct_name(st), _STAT_LABEL_UNIT.get(st, ('', ''))[1], default, present_all))
        for f in sv:
            if f == '__scalar__':
                continue
            label, unit = _STAT_LABEL_UNIT.get(f, (_display_field(f), ''))
            default = _mode(sv[f])
            present_all = sc.get(f, 0) >= total_parts
            fields.append((f, label, unit, default, present_all))
        schema.append((st, _stat_struct_name(st), fields))

    _TYPE_SCHEMA_CACHE[part_type] = schema
    return schema


_TYPE_AERO_CACHE: dict = {}


def _type_aero_fields(part_type: str) -> tuple[list, list]:
    """Return (lift_field_names, drag_field_names) that a part TYPE can carry.

    Union across all parts of the type, in a stable order. Used so every part
    of a type renders the same Aero rows (with '-' where that specific part
    has no value), instead of only parts that happen to carry aero data.
    """
    if part_type in _TYPE_AERO_CACHE:
        return _TYPE_AERO_CACHE[part_type]
    _load_ref_data()
    lift: list = []
    drag: list = []
    for rd in _REF_PARTS.values():
        if rd.get('type') != part_type:
            continue
        for f in (rd.get('stats') or {}):
            if f in _AERO_LIFT_FIELDS and f not in lift:
                lift.append(f)
            elif f in _AERO_DRAG_FIELDS and f not in drag:
                drag.append(f)
    _TYPE_AERO_CACHE[part_type] = (lift, drag)
    return lift, drag


def _mode(vals: list):
    """Mode (most common) value, stable on tie."""
    if not vals:
        return None
    counts: dict = {}
    for v in vals:
        k = _norm_val(v)
        counts[k] = counts.get(k, 0) + 1
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    # best is a normalized key; return a real value matching it
    for v in vals:
        if _norm_val(v) == best:
            return v
    return vals[0]


def _fmt_signed(v) -> str:
    """Signed display for a ±% delta: -40 -> '-40', 22.5 -> '+22.5'."""
    if abs(v) < 1e-9:
        return '0'
    s = _fmt_number(v)
    return f"+{s}" if v > 0 else s


def _render_part_stats(p: Part) -> str:
    """Render a part's tuning stats as reader-friendly DokuWiki tables.

    - An Aero section shows whole-vehicle drag % / lift+downforce coefficients
      (force formula applied at 200 km/h).
    - Every other stat struct of the part's type is rendered with a
      'Stat | Value' table showing ALL fields of the type; fields whose value
      equals the type's default are shown as '-' (or their % default), per the
      reference convention. Fields that only *some* parts of the type carry
      (e.g. engine CoolingEfficiency/StarterRPM) are omitted entirely when a
      given part lacks them.
    """
    lines = ["===== Stats ====="]
    stats = p.stats or {}

    # --- Aero section (type-driven: every aero field the type can have) ---
    lift_keys, drag_keys = _type_aero_fields(p.part_type)
    aero_lift = {f: stats.get(f) for f in lift_keys if f in stats and stats[f] is not None}
    aero_drag = {f: stats.get(f) for f in drag_keys if f in stats and stats[f] is not None}

    # Only emit the Aero section if this part type can carry aero data at all.
    if lift_keys or drag_keys:
        lines.append("")
        lines.append("==== Aero ====")
        lines.append("^ Stat ^ Value ^")
        for f in drag_keys:
            label = _AERO_DRAG_FIELDS[f]
            val = aero_drag.get(f)
            if val is None or val == '':
                lines.append(f"| {label} | - |")
                continue
            # (mult - 1) * 100 % of base; ×1.5 only for Air Drag when the part
            # has any lift coefficient (in-game head-up display). Trailer
            # Air Drag / Front Damage are plain ±% from 100.
            drag_pct = (val - 1.0) * 100
            if f == 'AirDragMultiplier' and (aero_lift or any(stats.get(k) for k in lift_keys)):
                drag_pct *= 1.5
            lines.append(f"| {label} | {_fmt_signed(drag_pct)}% |")
        for f in lift_keys:
            label, _ = _AERO_LIFT_FIELDS[f]
            val = aero_lift.get(f)
            if val is None or val == '':
                lines.append(f"| {label} | - |")
                continue
            coef = float(val)
            force = 7.098e-7 * (200 ** 2) * coef  # force_kg at 200 km/h
            if f == 'AeroLift':
                kind = 'downforce' if coef < 0 else 'lift'
                lines.append(f"| {label} | {_trim_number(coef)} ({abs(force):.1f} kg {kind} @ 200 km/h) |")
            else:
                # Front/Rear Aero Lift: coefficient + kg force, no direction word.
                lines.append(f"| {label} | {_trim_number(coef)} ({abs(force):.1f} kg @ 200 km/h) |")
        lines.append("")

    # --- Other stat structs: all fields of the type, '-' for missing ---
    schema = _build_type_schema(p.part_type) if p.part_type else []
    for struct, head, fields in schema:
        sval = stats.get(struct)
        rows = []  # data rows only; empty tables are omitted entirely
        for field, label, unit, default, present_all in fields:
            if field == '__scalar__':
                value = sval if not isinstance(sval, dict) else None
                if value is None or value == '':
                    if present_all:
                        rows.append(f"| {label} | - |")
                    # present-on-some scalar struct: omit silently
                    continue
                rows.append(f"| {label} | {_fmt_stat_value(field, value, unit)} |")
                continue
            # Field present on this part -> always show its real value.
            if isinstance(sval, dict) and field in sval and sval[field] is not None and sval[field] != '':
                value = sval[field]
                if field == 'DefaultGearIndex' and isinstance(sval.get('Gears'), list):
                    # The "default gear" is the gear whose name equals the index.
                    name = str(value)
                    for g in sval['Gears']:
                        if str(g.get('Name')) == name:
                            value = g['Name']
                            break
                rows.append(f"| {label} | {_fmt_stat_value(field, value, unit)} |")
            # Field absent -> the part uses the game's default for it.
            elif not present_all:
                # Only some parts of this type carry the field (e.g. engine
                # CoolingEfficiency); a part without it uses the editor default,
                # so omit the row rather than showing a fabricated value.
                continue
            elif unit == '%':
                rows.append(f"| {label} | 100% |")
            elif unit == '±':
                rows.append(f"| {label} | ±0% |")
            else:
                rows.append(f"| {label} | - |")
        # A schema entry whose every field is dropped (e.g. Wheel = meshes only,
        # Headlight = light anim) yields zero rows; render no table at all.
        if not rows:
            continue
        lines.append("")
        lines.append(f"==== {head} ====")
        lines.append("^ Stat ^ Value ^")
        lines.extend(rows)
    return '\n'.join(lines)


def _fmt_stat_value(field: str, value, unit: str) -> str:
    """Format a single stat value based on its type (vector/list/scalar)."""
    mult = _STAT_MULT.get(field, 1)
    if isinstance(value, dict):
        if unit == 'vec':
            return _fmt_vec_dims(value)
        if unit == 'rm':
            return _fmt_rng(value)
        body = _fmt_vec(value)
        if body == '0, 0, 0':
            return '—'
        return f"{body} {unit}".rstrip() if unit else body
    if isinstance(value, list):
        return _fmt_list(value)
    if isinstance(value, str):
        if value in _ENUM_HUMANIZE_OVERRIDE or '::' in value or field in _STAT_BOOL_FIELDS:
            return _humanize_enum(value)
        return value
    if isinstance(value, (int, float)) and mult != 1:
        value = value * mult
    return _fmt_simple_value(value, unit)


def generate_parts_index(parts: list[Part]) -> str:
    """Generate a part index page grouped by part type."""
    lines = [
        "====== List of Vehicle Parts ======",
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
        for p in sorted(by_type[pt], key=_natural_part_key):
            slug = _part_slug(p.id)
            mass = _fmt_weight(p.mass_kg) if p.mass_kg else '—'
            lines.append(f"| [[parts:{slug}|{_part_display_name(p)}]] | {_fmt_cost(p.cost)} | {mass} |")
        lines.append("")

    return '\n'.join(lines) + '\n'


def generate_vehicle_index(vehicles: list[Vehicle], slug_map: dict[str, str]) -> str:
    """Generate a vehicle index page grouped by type."""
    lines = [
        "====== List of Vehicles ======",
        "",
        f"There are {len(vehicles)} vehicles in [[:motor_town|Motor Town]]. For the full data see [[:vehicle_comparison|vehicle comparison table]].",
        "",
    ]

    # Group by type
    by_type: dict[str, list[Vehicle]] = {}
    for v in vehicles:
        vtype = _humanize_vehicle_type(v.vehicle_type)
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
        "====== Vehicle Comparison Table ======",
        "",
        "^ Name ^ Type ^ Cost ^ Drivetrain ^ Chassis Weight ^ Total Weight ^ Drag ^",
    ]

    for v in sorted(vehicles, key=lambda x: (_humanize_vehicle_type(x.vehicle_type), x.name)):
        slug = slug_map.get(v.id, _name_to_slug(v.name))
        drivetrain = _get_drivetrain(v.default_parts)
        lines.append(
            f"| [[vehicles:{slug}|{v.name}]] "
            f"| {_humanize_vehicle_type(v.vehicle_type)} "
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
    slug: str = '',
) -> str:
    """Merge system-generated content with existing user content for a vehicle page."""

    if existing_text is None:
        # Brand new page — generate with placeholders
        return _build_fresh_vehicle_page(vehicle, slug)

    sections = parse_page(existing_text)

    # Extract image + user-curated lines from existing infobox
    existing_image = None
    existing_infobox = None
    for sec in sections:
        if sec.name == 'infobox':
            existing_image = extract_infobox_image(sec.content)
            existing_infobox = sec.content
            break

    # Build the merged page
    parts = []

    # 1. Infobox
    parts.append(generate_vehicle_infobox(vehicle, existing_image, existing_infobox))
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
    parts.append(generate_vehicle_specs(vehicle, slug))
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


def _build_fresh_vehicle_page(vehicle: Vehicle, slug: str = '') -> str:
    """Build a brand new vehicle page with placeholders."""
    parts = []

    parts.append(generate_vehicle_infobox(vehicle))
    parts.append("")
    parts.append(generate_vehicle_heading(vehicle))
    parts.append("")
    parts.append(generate_vehicle_specs(vehicle, slug))
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
    vehicles = load_vehicles(conn, include_hidden=True)
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

        # The Wikipedia-style Installable Parts sub-page exists for every vehicle,
        # including hidden ones (trailers, karts, etc.).
        sub_slug = "installable_parts"
        sub_path = vehicles_dir / slug / f"{sub_slug}.txt"
        sub_text = generate_installable_parts_page(v, slug)
        sub_existing = sub_path.read_text(encoding='utf-8') if sub_path.exists() else None
        if sub_existing != sub_text:
            if dry_run:
                print(f"  {'CREATE' if sub_existing is None else 'UPDATE'}: vehicles/{slug}/{sub_slug}.txt")
            else:
                sub_path.parent.mkdir(parents=True, exist_ok=True)
                sub_path.write_text(sub_text, encoding='utf-8')
                print(f"  {'CREATE' if sub_existing is None else 'UPDATE'}: vehicles/{slug}/{sub_slug}.txt")

        # Hidden vehicles don't get their main page rewritten (only the sub-page).
        if v.is_hidden:
            continue

        page_path = vehicles_dir / f"{slug}.txt"

        existing_text = None
        if page_path.exists():
            existing_text = page_path.read_text(encoding='utf-8')

        try:
            new_text = merge_vehicle_page(existing_text, v, slug)
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

    # Vehicle display names come from the reference catalog (pak) inside
    # load_vehicles, which is authoritative. Do NOT re-override with stale
    # wiki page names (that reverted 'Jemusi Logger' back to 'Jemusi').

    index_pages = {
        'list_of_vehicles.txt': generate_vehicle_index(vehicles, slug_map),
        'vehicle_comparison.txt': generate_vehicle_comparison(vehicles, slug_map),
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

    # Remove orphaned part pages: pages in parts/ whose slug no longer maps to a
    # part in the authoritative catalog. When a part_filter is set we skip
    # cleanup (single-part inspection runs shouldn't delete siblings).
    if not part_filter and parts_dir.exists():
        valid_slugs = {_part_slug(p.id) for p in parts if not part_filter or p.id == part_filter}
        for page in parts_dir.glob('*.txt'):
            slug = page.stem
            if slug not in valid_slugs:
                stats['removed'] = stats.get('removed', 0) + 1
                if dry_run:
                    print(f"  REMOVE: parts/{page.name}")
                else:
                    page.unlink()
                    print(f"  REMOVE: parts/{page.name}")

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
