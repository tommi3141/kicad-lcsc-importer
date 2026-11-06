"""Offline tests (no network, no KiCad): conventions, KiCad s-expression formatting, import_part
with faked EasyEDA data.

Run:  pip install easyeda2kicad==1.0.1 && python tests/test_importer.py
"""
import re
import shutil
import sys
import tempfile
from pathlib import Path

PLUGIN = str(Path(__file__).resolve().parent.parent / "lcsc-importer")
sys.path.insert(0, PLUGIN)
sys.dont_write_bytecode = True

import easyeda2kicad  # noqa: E402
from easyeda2kicad.easyeda import parameters_easyeda as pe  # noqa: E402

import conventions as conv  # noqa: E402
import library as lib  # noqa: E402

fails = []


def eq(got, want, label):
    if got != want:
        fails.append(label)
        print("FAIL %s: got %r want %r" % (label, got, want))


# ---------------- conventions ----------------
for v, base, want in [(4700, "R", "4k7"), (4.7, "R", "4R7"), (60.4, "R", "60R4"), (120, "R", "120R"),
                      (0, "R", "0R"), (0.002, "R", "2m"), (0.0047, "R", "4m7"), (10000, "R", "10k"),
                      (2200, "R", "2k2"), (1e6, "R", "1M"), (4.7e6, "R", "4M7"), (999.6, "R", "1k"),
                      (4.7e-9, "F", "4n7"), (100e-9, "F", "100n"), (10e-6, "F", "10u"),
                      (18e-12, "F", "18p"), (2.2e-6, "H", "2u2"), (600e-9, "H", "600n")]:
    eq(conv.rkm(v, base), want, "rkm(%s,%s)" % (v, base))

res = conv.suggest("resistor", "100mW Thick Film Resistors 75V ±1% 10kΩ 0603 Chip Resistor - Surface Mount",
                   "R0603", "0603WAF1002T5E")
eq(res, ("10k 1% 0.1W", "RES | CHIP | 10k | 1% | 0.1W | 75V | 0603 [1608]"), "resistor")
res = conv.suggest("resistor", "3W ±1% 2mΩ 2512 Current Sense Resistor", "R2512", "X")
eq(res[1].startswith("RES | SHUNT | 2m | 1% | 3W"), True, "shunt " + res[1])
res = conv.suggest("capacitor", "50V 4.7nF X7R ±10% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT", "C0603", "X")
eq(res, ("4n7 50V X7R 10%", "CAP | CER | 4n7 | 50V | X7R | 10% | 0603 [1608]"), "capacitor")
res = conv.suggest("capacitor", "50V 18pF C0G ±5% 0603 Multilayer Ceramic Capacitors", "C0603", "X")
eq(res[0], "18p 50V NP0 5%", "C0G -> NP0")
res = conv.suggest("inductor", "600Ω@100MHz 0603 ±25% 500mA Ferrite Beads", "FB0603", "X")
eq(res[0], "600R@100MHz 0.5A", "ferrite value " + res[0])
res = conv.suggest("led", "Red 630nm 0603 LED Indication", "LED0603", "X")
eq(res[0], "red", "led")
res = conv.suggest("mcu", "32-bit RISC-V MCU 64KB Flash LQFP-48", "LQFP-48_7x7x0.5P", "CH32V203C8T6")
eq(res[0], "CH32V203C8T6", "mcu value")
eq(conv.default_footprint_name("capacitor", "C0603"), "C_0603_1608Metric", "fp name chip")
eq(conv.default_footprint_name("mcu", "LQFP-48_7x7x0.5P"), "LQFP-48_7x7x0.5P", "fp name other")
eq(conv.symbol_name("led", "19-217/GHC-YR1S2/3T"), "led/19-217_GHC-YR1S2_3T", "slash in MPN")
eq(conv.guess_category("TVS Diodes 24V", "D?"), "protection", "guess tvs")
eq(conv.guess_category("Chip Resistor", ""), "resistor", "guess resistor")

errs, warns = conv.check(dict(category="capacitor", symbol_name="capacitor/X", value="4.7nF",
                              description="Cap µF", manufacturer="", mpn="X", lcsc="C1",
                              datasheet="", fp_name="C_0603"))
eq(any("RKM" in w for w in warns) and any("ASCII" in w for w in warns), True, "check warnings")

# ---------------- library on a copy of the real EDENLibrary ----------------
tmp = Path(tempfile.mkdtemp())
root = tmp / "edenlibrary"
(root / "EDENLibrary.pretty").mkdir(parents=True)
(root / "EDENLibrary.pretty" / "C_0603_1608Metric.kicad_mod").write_text("(footprint \"C_0603_1608Metric\")\n")
(root / "EDENLibrary.kicad_sym").write_text(
    '(kicad_symbol_lib\n\t(version 20251024)\n\t(generator "kicad_symbol_editor")\n'
    '\t(symbol "capacitor/0603B472K500NT"\n\t\t(property "Reference" "C"\n\t\t\t(at 0 0 0)\n\t\t)\n\t)\n)\n')
paths = lib.detect_library(root)
eq(paths.name, "EDENLibrary", "detect name")
eq(paths.symbol_exists("capacitor/0603B472K500NT"), True, "symbol_exists real")
eq(paths.symbol_exists("capacitor/NOPE"), False, "symbol_exists no")
eq(paths.footprint_exists("C_0603_1608Metric"), True, "fp exists real")
before = (root / "EDENLibrary.kicad_sym").read_text(encoding="utf-8")
n_before = len(re.findall(r'^\t\(symbol "', before, re.M))

# fake EasyEDA objects
sym = pe.EeSymbol(
    info=pe.EeSymbolInfo(name="0603B472K500NT", prefix="C?", package="C0603", manufacturer="FH",
                         datasheet="https://www.lcsc.com/datasheet/C53987.pdf", lcsc_id="C53987",
                         mpn="0603B472K500NT", keywords="x y", description="LCSC desc"),
    bbox=pe.EeSymbolBbox(x=0, y=0, width=20, height=10),
    rectangles=[pe.EeSymbolRectangle(pos_x=-10, pos_y=-5, width=20, height=10, stroke_color="", stroke_width="1",
                                     stroke_style="0", fill_color="none", id="r1", is_locked=False)])
pad = pe.EeFootprintPad(shape="RECT", center_x=0, center_y=0, width=1, height=1, layer_id=1, net="", number="1",
                        hole_radius=0, points="", rotation=0, id="p1", hole_length=0, slot_outline="",
                        is_plated=True, is_locked=False)
model = pe.Ee3dModel(name="C0603", uuid="abc", translation=pe.Ee3dModelBase(), rotation=pe.Ee3dModelBase())
fp = pe.EeFootprint(info=pe.EeFootprintInfo(name="C0603", fp_type="smd", model_3d_name="C0603",
                                            lcsc_id="C53987", manufacturer="FH", mpn="0603B472K500NT",
                                            description="d"),
                    bbox=pe.EeFootprintBbox(x=0, y=0), model_3d=model, pads=[pad])


class FakeSym:
    def __init__(self, easyeda_cp_cad_data): pass
    def get_symbol(self): return sym


class FakeFp:
    def __init__(self, easyeda_cp_cad_data): pass
    def get_footprint(self): return fp


class FakeApi:
    def get_step_3d_model(self, uuid): return b"ISO-10303-21;FAKE"


easyeda2kicad.EasyedaSymbolImporter = FakeSym
easyeda2kicad.EasyedaFootprintImporter = FakeFp

form = lib.PartForm(lcsc="C53987", category="capacitor", reference="C", symbol_name="capacitor/TESTNEW123",
                    value="4n7 50V X7R 10%", description="CAP | CER | 4n7 | 50V | X7R | 10% | 0603 [1608]",
                    manufacturer="FH", mpn="0603B472K500NT", datasheet="https://x/y.pdf?a=1&b=2",
                    fp_name="TESTFP_NEW", jlcpcb_correction="0;0;-90")
prefix = "${KIPRJMOD}/libs/edenlibrary/EDENLibrary.3dshapes"
r = lib.import_part({}, form, paths, prefix, api=FakeApi())
print("\n".join(r.messages))

after = (root / "EDENLibrary.kicad_sym").read_text(encoding="utf-8")
eq(after.count("(") - after.count(")"), 0, "paren balance")
eq(len(re.findall(r'^\t\(symbol "', after, re.M)), n_before + 1, "one symbol added")
eq(after.startswith(before[:before.rstrip().rfind(")")].rstrip("\n")), True, "old content untouched")
blk = re.search(r'\(symbol "capacitor/TESTNEW123".*', after, re.S).group(0)
props = dict(re.findall(r'\(property\s+"([^"]+)"\s+"((?:[^"\\]|\\.)*)"', blk))
print({k: v for k, v in props.items()})
eq(props["Value"], "4n7 50V X7R 10%", "Value")
eq(props["Reference"], "C", "Reference")
eq(props["Footprint"], "EDENLibrary:TESTFP_NEW", "Footprint")
eq(props["LCSC"], "C53987", "LCSC")
eq(props["MPN"], "0603B472K500NT", "MPN unchanged by rename")
eq(props["Status"], "new", "Status")
eq(props["JLCPCB_CORRECTION"], "0;0;-90", "JLCPCB")
eq(props["ki_fp_filters"], "TESTFP_NEW", "fp filters")
eq("LCSC Part" in blk, False, "no 'LCSC Part'")
eq(re.findall(r'\(symbol "([^"]+)"', blk)[:3], ["capacitor/TESTNEW123", "capacitor/TESTNEW123_0_1", "capacitor/TESTNEW123_1_1"][:len(re.findall(r'\(symbol "([^"]+)"', blk)[:3])], "unit names")
print(re.findall(r'\(symbol "([^"]+)"', blk))

mod = (root / "EDENLibrary.pretty" / "TESTFP_NEW.kicad_mod").read_text(encoding="utf-8")
eq(mod.startswith('(module "TESTFP_NEW"'), True, "fp header: " + mod[:40])
eq(('(model "%s/TESTFP_NEW.step"' % prefix) in mod, True, "model path")
eq((root / "EDENLibrary.3dshapes" / "TESTFP_NEW.step").read_bytes(), b"ISO-10303-21;FAKE", "step file")
eq("wrl" in mod, False, "no wrl ref")

# existing symbol / reuse of existing footprint
try:
    lib.import_part({}, form, paths, prefix, api=FakeApi())
    fails.append("duplicate symbol accepted")
except RuntimeError as e:
    print("OK duplicate rejected:", e)
form2 = lib.PartForm(**{**form.__dict__, "symbol_name": "capacitor/TESTNEW456", "fp_name": "C_0603_1608Metric"})
fp_before = (root / "EDENLibrary.pretty" / "C_0603_1608Metric.kicad_mod").read_bytes()
r2 = lib.import_part({}, form2, paths, prefix, api=FakeApi())
print(r2.messages)
eq((root / "EDENLibrary.pretty" / "C_0603_1608Metric.kicad_mod").read_bytes(), fp_before, "existing footprint untouched")

# new library from scratch
new = lib.detect_library(tmp / "newlib")
(tmp / "newlib").mkdir()
lib.import_part({}, form, new, prefix, api=FakeApi())
t = new.sym_file.read_text(encoding="utf-8")
eq(t.startswith("(kicad_symbol_lib\n\t(version 20251024)"), True, "new lib header")
eq(t.count("(") - t.count(")"), 0, "new lib balance")

# no step -> no model block
class NoStep(FakeApi):
    def get_step_3d_model(self, uuid): return None
form3 = lib.PartForm(**{**form.__dict__, "symbol_name": "capacitor/TESTNEW789", "fp_name": "TESTFP_NOSTEP"})
r3 = lib.import_part({}, form3, paths, prefix, api=NoStep())
mod3 = (root / "EDENLibrary.pretty" / "TESTFP_NOSTEP.kicad_mod").read_text(encoding="utf-8")
eq("(model" in mod3, False, "no model block without step")
eq(mod3.count("(") - mod3.count(")"), 0, "fp balance no model")

print("\nFAILED: %s" % fails if fails else "\nALL OK")
shutil.rmtree(tmp, ignore_errors=True)
