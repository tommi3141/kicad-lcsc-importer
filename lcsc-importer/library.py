"""Reading EasyEDA data (via easyeda2kicad) and writing it into a KiCad library folder."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import conventions as conv

SETTINGS_FILE = Path.home() / ".kicad_lcsc_importer.json"
NEW_LIB_VERSION = 20251024  # KiCad 10 symbol format, used when the .kicad_sym does not exist yet


# --------------------------------------------------------------------------
# Library folder
# --------------------------------------------------------------------------
@dataclass
class LibraryPaths:
    root: Path
    name: str

    @property
    def sym_file(self):
        return self.root / ("%s.kicad_sym" % self.name)

    @property
    def pretty(self):
        return self.root / ("%s.pretty" % self.name)

    @property
    def shapes(self):
        return self.root / ("%s.3dshapes" % self.name)

    def footprint_exists(self, fp_name):
        return (self.pretty / ("%s.kicad_mod" % fp_name)).is_file()

    def symbol_exists(self, sym_name):
        if not self.sym_file.is_file():
            return False
        text = self.sym_file.read_text(encoding="utf-8")
        return re.search(r'\(symbol\s+"%s"' % re.escape(sym_name), text) is not None


def detect_library(root):
    """Library name = stem of an existing .kicad_sym / .pretty / .3dshapes, else the folder name."""
    root = Path(root)
    for pattern in ("*.kicad_sym", "*.pretty", "*.3dshapes"):
        found = sorted(root.glob(pattern)) if root.is_dir() else []
        if found:
            return LibraryPaths(root, found[0].stem)
    return LibraryPaths(root, root.name)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------
# EasyEDA data
# --------------------------------------------------------------------------
@dataclass
class PartInfo:
    lcsc: str
    title: str = ""
    description: str = ""
    package: str = ""
    manufacturer: str = ""
    mpn: str = ""
    datasheet: str = ""
    prefix: str = ""


def normalize_lcsc(text):
    t = (text or "").strip().upper()
    if re.fullmatch(r"\d+", t):
        t = "C" + t
    return t if re.fullmatch(r"C\d+", t) else ""


def fetch_part(lcsc, api=None):
    """Returns (cad_data, PartInfo). Raises RuntimeError with a readable message."""
    from easyeda2kicad import EasyedaApi, EasyedaSymbolImporter

    api = api or EasyedaApi()
    cad = api.get_cad_data_of_component(lcsc_id=lcsc)
    if not cad:
        raise RuntimeError("Keine Daten für %s gefunden (Nummer falsch oder keine Internetverbindung)." % lcsc)
    sym = EasyedaSymbolImporter(easyeda_cp_cad_data=cad).get_symbol()
    i = sym.info
    return cad, PartInfo(lcsc=lcsc, title=cad.get("title", ""), description=i.description,
                         package=i.package, manufacturer=i.manufacturer, mpn=i.mpn,
                         datasheet=i.datasheet, prefix=i.prefix.replace("?", ""))


# --------------------------------------------------------------------------
# Text post-processing of the easyeda2kicad output
# --------------------------------------------------------------------------
def esc(text):
    """Escape a value for a quoted KiCad s-expression string."""
    return (text or "").replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")


def postprocess_symbol(text, old_name, new_name, value):
    """Rename the symbol and its units, set Value, rename 'LCSC Part' to 'LCSC'."""
    text = re.sub(r'\(symbol\s+"%s((?:_\d+_\d+)?)"' % re.escape(old_name),
                  lambda m: '(symbol "%s%s"' % (esc(new_name), m.group(1)), text)
    text = re.sub(r'(\(property\s+"Value"\s+)"(?:[^"\\]|\\.)*"',
                  lambda m: '%s"%s"' % (m.group(1), esc(value)), text, count=1)
    return text.replace('"LCSC Part"', '"LCSC"')


def postprocess_footprint(text, fp_name, model_path):
    """Plain footprint name, STEP model path (or no model block if model_path is None)."""
    text = re.sub(r"^\(module\s+\S+", '(module "%s"' % fp_name, text, count=1)
    text = re.sub(r"\(fp_text value \S+", "(fp_text value %s" % fp_name, text, count=1)
    if model_path:
        text = re.sub(r'\(model\s+"[^"]*"', lambda m: '(model "%s"' % model_path, text, count=1)
    else:
        text = re.sub(r'\t\(model "[^"]*"\n(?:\t\t.*\n)*?\t\)\n', "", text, count=1)
    return text


def _tokenize(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "()":
            yield c
            i += 1
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            yield text[i:j + 1]
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            yield text[i:j]
            i = j


def _parse(tokens):
    stack, cur = [], []
    for tok in tokens:
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(tok)
    return cur


_PROP_ORDER = ["Reference", "Value", "Footprint", "Datasheet", "Description", "Manufacturer", "MPN",
               "LCSC", "Status", "JLCPCB_CORRECTION", "ki_keywords", "ki_fp_filters"]
_FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def _has(node, head):
    return any(isinstance(c, list) and c and c[0] == head for c in node)


def canonicalize_symbol(sym, modern):
    """Match what KiCad 10 writes for a symbol: property order, hidden fields at (0 0 0),
    show_name/do_not_autoplace in properties, in_pos_files/duplicate_pin_numbers_are_jumpers."""
    props = [c for c in sym if isinstance(c, list) and c and c[0] == "property"]

    def order(p):
        name = p[1].strip('"')
        return _PROP_ORDER.index(name) if name in _PROP_ORDER else len(_PROP_ORDER)

    props.sort(key=order)
    for p in props:
        at = next((c for c in p if isinstance(c, list) and c[0] == "at"), None)
        if at is not None and _has(p, "hide"):
            at[1:] = ["0", "0", "0"]
        if modern and at is not None:
            pos = p.index(at) + 1
            for token in (["show_name", "no"], ["do_not_autoplace", "no"]):
                if not _has(p, token[0]):
                    p.insert(pos, list(token))
                    pos += 1
    out, placed = [], False
    for c in sym:
        if isinstance(c, list) and c and c[0] == "property":
            if not placed:
                out.extend(props)
                placed = True
        else:
            out.append(c)
            if modern and isinstance(c, list) and c[:2] == ["on_board", "yes"]:
                for token in (["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"]):
                    if not _has(sym, token[0]):
                        out.append(list(token))
    sym[:] = out


def kicad_format(text, depth=1, modern=None):
    """Re-emit s-expressions the way KiCad writes them: tab indent, lists without sub-lists on one
    line, all others with the head atoms on the first line and each child on its own line."""
    out = []

    def norm(atom):
        if _FLOAT_RE.match(atom):
            atom = atom.rstrip("0").rstrip(".")
            return "0" if atom == "-0" else atom
        return atom

    def emit(node, d):
        pad = "\t" * d
        node = [x if isinstance(x, list) else norm(x) for x in node]
        if not any(isinstance(x, list) for x in node):
            out.append("%s(%s)" % (pad, " ".join(node)))
            return
        k = 0
        while not isinstance(node[k], list):
            k += 1
        out.append("%s(%s" % (pad, " ".join(node[:k])))
        if node[0] == "pts" and all(isinstance(c, list) and c[0] == "xy" for c in node[1:]):
            pts = ["(%s)" % " ".join(c) for c in node[1:]]
            line = []
            for k, item in enumerate(pts):
                line.append(item)
                # KiCad wraps after every 5 points, but never leaves a single point alone
                if (k + 1) % 5 == 0 and len(pts) - k - 1 >= 2:
                    out.append("%s\t%s" % (pad, " ".join(line)))
                    line = []
            if line:
                out.append("%s\t%s" % (pad, " ".join(line)))
            out.append("%s)" % pad)
            return
        for child in node[k:]:
            if isinstance(child, list):
                emit(child, d + 1)
            else:
                out.append("%s\t%s" % (pad, child))
        out.append("%s)" % pad)

    for node in _parse(_tokenize(text)):
        if modern is not None:
            canonicalize_symbol(node, modern)
        emit(node, depth)
    return "\n".join(out)


def _kicad_cli():
    dirs = [os.path.dirname(sys.executable), sys.base_prefix,
            os.path.dirname(getattr(sys, "_base_executable", "") or "")]
    for d in dirs:
        for exe in ("kicad-cli.exe", "kicad-cli"):
            p = os.path.join(d, exe) if d else ""
            if p and os.path.isfile(p):
                return p
    return shutil.which("kicad-cli")


def upgrade_footprint(text, name):
    """Let kicad-cli convert the legacy (module ...) text to the current format.

    Works on a temporary one-footprint library so existing footprints are never touched.
    Returns (text, upgraded)."""
    cli = _kicad_cli()
    if not cli:
        return text, False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pretty = Path(tmp) / "upgrade.pretty"
            pretty.mkdir()
            f = pretty / ("%s.kicad_mod" % name)
            f.write_text(text, encoding="utf-8")
            r = subprocess.run([cli, "fp", "upgrade", "--force", str(pretty)], capture_output=True,
                               timeout=60, creationflags=0x08000000 if sys.platform == "win32" else 0)
            new = f.read_text(encoding="utf-8")
            if r.returncode == 0 and new.lstrip().startswith("(footprint"):
                return new, True
    except (OSError, subprocess.SubprocessError):
        pass
    return text, False


def insert_symbol(lib_text, sym_text, modern=True):
    """Insert a symbol before the final closing parenthesis of a .kicad_sym file."""
    end = lib_text.rstrip().rfind(")")
    if end < 0:
        raise ValueError("Ungültige .kicad_sym-Datei (keine schließende Klammer).")
    return lib_text[:end].rstrip("\n") + "\n" + kicad_format(sym_text, modern=modern) + "\n" + lib_text[end:]


def _write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------
@dataclass
class PartForm:
    lcsc: str
    category: str
    reference: str
    symbol_name: str
    value: str
    description: str
    manufacturer: str
    mpn: str
    datasheet: str
    fp_name: str
    status: str = "new"
    jlcpcb_correction: str = ""


@dataclass
class ImportResult:
    messages: list = field(default_factory=list)
    ok: bool = True


def import_part(cad, form, paths, model_prefix, api=None):
    """Write symbol, footprint and 3D model into the library. Nothing existing is overwritten."""
    from easyeda2kicad import (Easyeda3dModelImporter, EasyedaApi, EasyedaFootprintImporter,
                               EasyedaSymbolImporter, Exporter3dModelKicad, ExporterFootprintKicad,
                               ExporterSymbolKicad)

    api = api or EasyedaApi()
    res = ImportResult()

    if paths.symbol_exists(form.symbol_name):
        raise RuntimeError("Symbol '%s' existiert bereits in %s. Vorhandene Symbole werden nicht "
                           "überschrieben." % (form.symbol_name, paths.sym_file.name))

    # ---- symbol (built in memory first, written last) ----
    ee_symbol = EasyedaSymbolImporter(easyeda_cp_cad_data=cad).get_symbol()
    old_name = ee_symbol.info.name
    info = ee_symbol.info
    info.prefix = form.reference
    info.package = form.fp_name
    info.manufacturer = esc(form.manufacturer)
    info.mpn = esc(form.mpn)
    info.datasheet = esc(form.datasheet)
    info.lcsc_id = esc(form.lcsc)
    info.keywords = ""
    info.description = esc(form.description)
    custom = {"Status": esc(form.status)}
    if form.jlcpcb_correction:
        custom["JLCPCB_CORRECTION"] = esc(form.jlcpcb_correction)
    custom["ki_fp_filters"] = esc(form.fp_name)
    if form.category in conv.NOT_IN_BOM:
        info.manufacturer = info.mpn = info.lcsc_id = ""

    version = None if paths.sym_file.is_file() else NEW_LIB_VERSION
    exporter = ExporterSymbolKicad(symbol=ee_symbol, lib_path=str(paths.sym_file), version=version,
                                   custom_fields=custom)
    sym_text = postprocess_symbol(exporter.export(footprint_lib_name=paths.name),
                                  old_name, form.symbol_name, form.value)

    # ---- footprint + 3D model (only if the footprint is new) ----
    fp_text = step_bytes = None
    if paths.footprint_exists(form.fp_name):
        res.messages.append("Footprint '%s' existiert bereits und wird wiederverwendet (nicht verändert)."
                            % form.fp_name)
    else:
        ee_fp = EasyedaFootprintImporter(easyeda_cp_cad_data=cad).get_footprint()
        if ee_fp.model_3d is not None:
            step_bytes = api.get_step_3d_model(uuid=ee_fp.model_3d.uuid)
        model_path = "%s/%s.step" % (model_prefix.rstrip("/"), form.fp_name) if step_bytes else None
        with tempfile.TemporaryDirectory() as tmp:
            tmp_file = os.path.join(tmp, "fp.kicad_mod")
            ExporterFootprintKicad(footprint=ee_fp).export(
                footprint_full_path=tmp_file, model_3d_path=model_prefix, model_3d_extension="step")
            with open(tmp_file, encoding="utf-8") as f:
                fp_text = postprocess_footprint(f.read(), form.fp_name, model_path)
        fp_text, upgraded = upgrade_footprint(fp_text, form.fp_name)
        if not upgraded:
            res.messages.append("Hinweis: Footprint liegt im alten Dateiformat vor (kicad-cli nicht "
                                "gefunden); KiCad konvertiert ihn beim ersten Speichern.")
        if not step_bytes:
            res.messages.append("Für dieses Bauteil gibt es bei EasyEDA kein 3D-Modell, "
                                "der Footprint hat keines.")

    # ---- write ----
    if fp_text is not None:
        _write_atomic(paths.pretty / ("%s.kicad_mod" % form.fp_name), fp_text)
        res.messages.append("Footprint geschrieben: %s.pretty/%s.kicad_mod" % (paths.name, form.fp_name))
    if step_bytes:
        paths.shapes.mkdir(parents=True, exist_ok=True)
        (paths.shapes / ("%s.step" % form.fp_name)).write_bytes(step_bytes)
        res.messages.append("3D-Modell geschrieben: %s.3dshapes/%s.step (Lage/Drehung im 3D-Viewer prüfen)"
                            % (paths.name, form.fp_name))
    if paths.sym_file.is_file():
        lib_text = paths.sym_file.read_text(encoding="utf-8")
    else:
        lib_text = ('(kicad_symbol_lib\n\t(version %d)\n\t(generator "kicad_symbol_editor")\n)\n'
                    % NEW_LIB_VERSION)
    _write_atomic(paths.sym_file, insert_symbol(lib_text, sym_text, modern=exporter.version >= NEW_LIB_VERSION))
    res.messages.insert(0, "Symbol geschrieben: %s (%s)" % (form.symbol_name, paths.sym_file.name))
    return res
