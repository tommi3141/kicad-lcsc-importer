"""Naming and field conventions of the EDENLibrary (see README of the library).

Pure Python, no KiCad or network access, so it can be unit tested on its own.
"""
import re

# category -> allowed reference prefixes (first one is the default)
CATEGORIES = {
    "resistor": ["R"],
    "capacitor": ["C"],
    "inductor": ["L", "FB"],
    "diode": ["D"],
    "led": ["LED"],
    "transistor": ["Q"],
    "protection": ["D", "RV", "F"],
    "mcu": ["U"],
    "logic": ["U"],
    "analog": ["U"],
    "interface": ["U"],
    "power": ["U", "PS"],
    "oscillator": ["Y"],
    "relay": ["K"],
    "switch": ["SW"],
    "connector": ["J"],
    "mechanical": ["H", "TP", "JP", "NT"],
    "graphic": ["G"],
}
NOT_IN_BOM = {"mechanical", "graphic"}  # no Manufacturer / MPN / LCSC required
STATUS_VALUES = ["new", "pcb-ok", "verified"]

IMPERIAL_TO_METRIC = {
    "01005": "0402", "0201": "0603", "0402": "1005", "0603": "1608", "0805": "2012",
    "1206": "3216", "1210": "3225", "1812": "4532", "2010": "5025", "2512": "6332",
}
CHIP_PREFIX = {"resistor": "R", "capacitor": "C", "inductor": "L", "led": "LED", "diode": "D"}

_NUM = r"(\d+(?:\.\d+)?)"
_PFX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
        "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9}
_SI = [(1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p")]
_IMPERIAL_RE = re.compile(r"(?<!\d)(01005|0201|0402|0603|0805|1206|1210|1812|2010|2512)(?!\d)")


# --------------------------------------------------------------------------
# Number formatting / parsing
# --------------------------------------------------------------------------
def rkm(value, base):
    """IEC 60062 (RKM) notation: rkm(4700, 'R') -> '4k7', rkm(4.7e-9, 'F') -> '4n7'.

    base is 'R' (ohm), 'F' (farad) or 'H' (henry). The unit itself is omitted.
    """
    if value == 0:
        return "0R" if base == "R" else "0"
    idx = len(_SI) - 1
    for i, (factor, _) in enumerate(_SI):
        if value / factor >= 0.9999999:
            idx = i
            break
    mant = float("%.3g" % (value / _SI[idx][0]))
    if mant >= 1000 and idx > 0:  # 999.6 rounds up to 1000 -> next prefix
        idx -= 1
        mant = float("%.3g" % (value / _SI[idx][0]))
    prefix = _SI[idx][1]
    if prefix == "":
        prefix = "R" if base == "R" else base
    whole, _, frac = ("%g" % mant).partition(".")
    return whole + prefix + frac


def _scaled(num, prefix):
    return float(num) * _PFX.get(prefix, 1.0)


def parse_capacitance(text):
    m = re.search(_NUM + r"\s*([pnuµμm]?)F(?![A-Za-z])", text)
    return _scaled(m.group(1), m.group(2)) if m else None


def parse_resistance(text):
    m = re.search(_NUM + r"\s*([mkKMG]?)\s*(?:Ω|Ω|[Oo]hms?|OHMS?|R(?![A-Za-z]))", text)
    return _scaled(m.group(1), m.group(2)) if m else None


def parse_inductance(text):
    m = re.search(_NUM + r"\s*([nuµμm]?)H(?![A-Za-z])", text)
    return _scaled(m.group(1), m.group(2)) if m else None


def parse_voltage(text):
    m = re.search(_NUM + r"\s*(m?)V(?![A-Za-z])", text)
    return _scaled(m.group(1), m.group(2)) if m else None


def parse_current(text):
    m = re.search(_NUM + r"\s*(m?)A(?![A-Za-z])", text)
    return _scaled(m.group(1), m.group(2)) if m else None


def parse_power(text):
    m = re.search(r"(\d+/\d+|" + _NUM + r")\s*(m?)W(?![A-Za-z])", text)
    if not m:
        return None
    raw = m.group(1)
    if "/" in raw:
        a, b = raw.split("/")
        val = float(a) / float(b)
    else:
        val = float(raw) * _PFX[m.group(3)]
    return val


def parse_tolerance(text):
    m = re.search(r"±\s*" + _NUM + r"\s*%", text)
    return m.group(1) if m else None


def parse_dielectric(text):
    m = re.search(r"\b(X7R|X5R|X6S|X7S|X7T|X8R|Y5V|Z5U|NP0|C0G|COG)\b", text, re.I)
    if not m:
        return None
    d = m.group(1).upper()
    return "NP0" if d in ("C0G", "COG") else d


def parse_frequency(text):
    m = re.search(_NUM + r"\s*([kM]?)Hz", text)
    return (m.group(1) + m.group(2) + "Hz") if m else None


def fmt(value, unit):
    """3.3 -> '3.3V', 0.1 -> '0.1W'"""
    return ("%.6g" % value) + unit


def ascii_only(text):
    for a, b in (("Ω", "Ohm"), ("Ω", "Ohm"), ("µ", "u"), ("μ", "u"),
                 ("±", "+-"), ("°", "deg"), ("℃", "degC")):
        text = text.replace(a, b)
    return text.encode("ascii", "ignore").decode("ascii")


def package_text(package):
    """'0603 [1608]' for chip sizes, otherwise the cleaned package name."""
    m = _IMPERIAL_RE.search(package or "")
    if m:
        return "%s [%s]" % (m.group(1), IMPERIAL_TO_METRIC[m.group(1)])
    return sanitize_name(package or "")


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------
def sanitize_name(text):
    """Footprint names: only A-Z a-z 0-9 - _ ."""
    return re.sub(r"[^A-Za-z0-9\-_.]+", "_", text or "").strip("_")


def symbol_name(category, mpn):
    return "%s/%s" % (category, (mpn or "").replace("/", "_"))


def default_footprint_name(category, package):
    m = _IMPERIAL_RE.search(package or "")
    if m and category in CHIP_PREFIX:
        return "%s_%s_%sMetric" % (CHIP_PREFIX[category], m.group(1), IMPERIAL_TO_METRIC[m.group(1)])
    return sanitize_name(package)


def default_model_prefix(root_folder_name, lib_name):
    return "${KIPRJMOD}/libs/%s/%s.3dshapes" % (root_folder_name, lib_name)


# --------------------------------------------------------------------------
# Category guess and suggestions for Value / Description
# --------------------------------------------------------------------------
_GUESS = [
    (r"resistor|shunt", "resistor"),
    (r"capacitor|mlcc", "capacitor"),
    (r"ferrite|inductor|choke", "inductor"),
    (r"\bleds?\b|light emitting", "led"),
    (r"\btvs\b|\besd\b|varistor|fuse|polyswitch", "protection"),
    (r"mosfet|transistor|\bbjt\b|\bigbt\b", "transistor"),
    (r"diode|rectifier|zener|schottky", "diode"),
    (r"crystal|oscillator|resonator", "oscillator"),
    (r"relay", "relay"),
    (r"switch|tactile|button", "switch"),
    (r"connector|header|terminal|socket|rj45|usb|plug|receptacle", "connector"),
    (r"microcontroller|\bmcu\b", "mcu"),
    (r"\bldo\b|regulator|dc-dc|converter|load switch|hot.?swap", "power"),
    (r"op.?amp|operational|comparator|voltage reference", "analog"),
    (r"transceiver|optocoupler|isolator|photocoupler", "interface"),
    (r"logic|gate|buffer|inverter|flip-flop", "logic"),
]
_PREFIX_GUESS = {"R": "resistor", "C": "capacitor", "L": "inductor", "FB": "inductor", "D": "diode",
                 "LED": "led", "Q": "transistor", "Y": "oscillator", "K": "relay", "SW": "switch",
                 "J": "connector", "F": "protection"}


def guess_category(description, prefix=""):
    low = (description or "").lower()
    for pattern, cat in _GUESS:
        if re.search(pattern, low):
            return cat
    return _PREFIX_GUESS.get((prefix or "").rstrip("?").upper(), "")


def _join(parts):
    return " | ".join(p for p in parts if p)


def _pct(tol):
    return "%s%%" % tol if tol else ""


def suggest(category, desc, package, mpn):
    """Best-effort proposal for (value, description) from the LCSC product description.

    The user reviews both in the dialog; unknown values are left out instead of guessed.
    """
    desc = desc or ""
    chip = _IMPERIAL_RE.search(package or "") or _IMPERIAL_RE.search(desc)
    pkg = package_text(chip.group(1)) if chip else package_text(package)
    low = desc.lower()

    if category == "resistor":
        r = parse_resistance(desc)
        tol, p, v = parse_tolerance(desc), parse_power(desc), parse_voltage(desc)
        cls = "SHUNT" if (r is not None and r < 0.1) or re.search(r"current sens|shunt", low) else "CHIP"
        rv = rkm(r, "R") if r is not None else ""
        value = " ".join(x for x in (rv, _pct(tol), fmt(p, "W") if p else "") if x)
        return value, _join(["RES", cls, rv, _pct(tol), fmt(p, "W") if p else "",
                             fmt(v, "V") if v else "", pkg])

    if category == "capacitor":
        c = parse_capacitance(desc)
        v, tol, diel = parse_voltage(desc), parse_tolerance(desc), parse_dielectric(desc)
        kind = "ALU" if re.search(r"alumin|electrolytic", low) else "FILM" if "film" in low else "CER"
        cv = rkm(c, "F") if c is not None else ""
        vs = fmt(v, "V") if v else ""
        value = " ".join(x for x in (cv, vs, diel or "", _pct(tol)) if x)
        return value, _join(["CAP", kind, cv, vs, diel or "", _pct(tol), pkg])

    if category == "inductor":
        i = parse_current(desc)
        istr = fmt(i, "A") if i else ""
        if re.search(r"ferrite|bead", low):
            z, f = parse_resistance(desc), parse_frequency(desc[desc.find("@"):]) if "@" in desc else None
            zs = ("%s@%s" % (rkm(z, "R"), f)) if z is not None and f else ""
            return " ".join(x for x in (zs, istr) if x), _join(["IND", "FERRITE", zs, istr, pkg])
        lval = parse_inductance(desc)
        ls = rkm(lval, "H") if lval is not None else ""
        kind = "CM CHOKE" if re.search(r"common.?mode", low) else "POWER"
        return " ".join(x for x in (ls, istr) if x), _join(["IND", kind, ls, istr, pkg])

    if category == "led":
        m = re.search(r"\b(red|green|blue|yellow|white|orange|amber|purple|pink|cyan|uv|ir)\b", low)
        color = m.group(1) if m else ""
        nm = re.search(r"(\d{3})\s*nm", desc)
        mcd = re.search(_NUM + r"\s*mcd", low)
        ma = re.search(r"(\d+(?:\.\d+)?)\s*mA", desc)
        deg = re.search(r"(\d+)\s*(?:°|deg)", desc)
        v = parse_voltage(desc)
        return color, _join(["LED", color.upper(), (nm.group(1) + "nm") if nm else "",
                             (mcd.group(1) + "mcd") if mcd else "", fmt(v, "V") if v else "",
                             (ma.group(1) + "mA") if ma else "", (deg.group(1) + "deg") if deg else "", pkg])

    if category == "oscillator":
        f = parse_frequency(desc) or ""
        cl = re.search(_NUM + r"\s*pF", desc)
        ppm = re.search(r"±\s*" + _NUM + r"\s*ppm", desc)
        cls = "OSC" if re.search(r"oscillator", low) and "crystal" not in low else "XTAL"
        return f, _join([cls, f, (cl.group(1) + "pF") if cl else "",
                         (ppm.group(1) + "ppm") if ppm else "", pkg])

    if category == "protection" and re.search(r"fuse|polyswitch", low):
        i, v = parse_current(desc), parse_voltage(desc)
        iv = " ".join(x for x in (fmt(i, "A") if i else "", fmt(v, "V") if v else "") if x)
        return iv, _join(["FUSE", fmt(i, "A") if i else "", fmt(v, "V") if v else "", pkg])

    # all other categories: value = MPN (to be shortened by hand), description = skeleton
    cls = _default_class(category, low)
    hint = ascii_only(desc).strip()
    return (mpn or ""), _join([cls, hint, pkg])


def _default_class(category, low):
    table = {
        "diode": "DIODE", "led": "LED", "mcu": "MCU", "logic": "LOGIC", "relay": "RELAY",
        "switch": "SWITCH", "connector": "CON", "mechanical": "MOUNTING HOLE", "graphic": "GRAPHIC",
    }
    if category == "transistor":
        return "BJT" if re.search(r"npn|pnp|bjt", low) and "mosfet" not in low else "MOSFET"
    if category == "protection":
        return "VARISTOR" if "varistor" in low else "FUSE" if "fuse" in low else "TVS"
    if category == "analog":
        return "COMP" if "comparator" in low else "VREF" if "reference" in low else "OPAMP"
    if category == "interface":
        return "OPTO" if re.search(r"opto|photocoupler", low) else "TRANSCEIVER"
    if category == "power":
        return "LOAD SWITCH" if "load switch" in low else "LDO" if re.search(r"\bldo\b", low) else "DCDC"
    return table.get(category, category.upper())


# --------------------------------------------------------------------------
# Validation (warnings only, the user decides)
# --------------------------------------------------------------------------
_RKM_RE = re.compile(r"^\d{1,3}(?:[RpnumkMG]\d{0,2}|[pnumkMGR])$")


def check(f):
    """f: dict with category, symbol_name, value, description, manufacturer, mpn, lcsc,
    datasheet, fp_name. Returns (errors, warnings)."""
    errors, warnings = [], []
    cat = f["category"]
    if cat not in CATEGORIES:
        errors.append("Kategorie wählen.")
    if not f["symbol_name"] or f["symbol_name"].endswith("/"):
        errors.append("Symbolname fehlt (MPN eintragen).")
    elif not re.match(r"^%s/[^\s\"]+$" % re.escape(cat), f["symbol_name"]):
        warnings.append("Symbolname soll '<kategorie>/<MPN>' sein.")
    if not f["fp_name"]:
        errors.append("Footprint-Name fehlt.")
    elif not re.match(r"^[A-Za-z0-9\-_.]+$", f["fp_name"]):
        errors.append("Footprint-Name: nur A-Z a-z 0-9 - _ . erlaubt.")
    if not f["value"]:
        errors.append("Value fehlt.")
    value = f["value"]
    if re.search(r"[^\x00-\x7f]", value):
        warnings.append("Value: nur ASCII ('u' statt µ, kein Ω).")
    if cat in ("resistor", "capacitor", "inductor") and value:
        first = value.split()[0]
        if not _RKM_RE.match(first.split("@")[0]):
            warnings.append("Value: Wert in RKM-Schreibweise erwartet (4n7, 2k2, 120R).")
    if cat == "led" and value and value != value.lower():
        warnings.append("Value einer LED: Farbe klein geschrieben.")
    desc = f["description"]
    if not desc:
        errors.append("Description fehlt.")
    else:
        if re.search(r"[^\x00-\x7f]", desc):
            warnings.append("Description: nur ASCII (Ohm statt Ω, deg statt °).")
        if " | " not in desc:
            warnings.append("Description: Aufbau '<KLASSE> | <Bauart> | ... | <Gehäuse>' erwartet.")
        if desc.rstrip().endswith("|"):
            warnings.append("Description: kein '|' am Ende.")
        if len(desc.split(" | ")) < 4 and cat not in ("mechanical", "graphic"):
            warnings.append("Description: Kennwerte laut Konvention prüfen/ergänzen.")
    if cat not in NOT_IN_BOM:
        if not f["manufacturer"]:
            warnings.append("Manufacturer fehlt.")
        if not f["mpn"]:
            errors.append("MPN fehlt.")
        if not re.match(r"^C\d+$", f["lcsc"] or ""):
            warnings.append("LCSC-Nummer fehlt oder hat falsches Format.")
    if not (f["datasheet"] or "").startswith("http"):
        warnings.append("Datasheet: URL fehlt.")
    return errors, warnings
