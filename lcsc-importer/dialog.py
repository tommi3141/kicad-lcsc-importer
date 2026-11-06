"""wxPython dialog: enter an LCSC number, review the proposed fields, add the part to a library."""
import threading
import traceback
from pathlib import Path

import wx

import conventions as conv
import library as lib

MAX_RECENT_LIBS = 10


class ImporterDialog(wx.Dialog):
    def __init__(self):
        super().__init__(None, title="LCSC Importer", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = lib.load_settings()
        self.cad = None
        self.info = None
        self.paths = None
        self.dirty = set()  # fields the user edited by hand: not overwritten by suggestions
        self.busy = False
        self._build()
        self.SetMinSize(self.FromDIP(wx.Size(640, 600)))
        self.SetSize(self.FromDIP(wx.Size(700, 700)))
        self.CentreOnScreen()
        last = self.settings.get("last_library", "")
        if last:
            self.lib_box.SetValue(last)
            self.on_library()
        self.lcsc.SetFocus()

    # ------------------------------------------------------------------ UI
    def _text(self, parent, name):
        t = wx.TextCtrl(parent)
        t.Bind(wx.EVT_TEXT, lambda e, n=name: self.on_edit(n))
        return t

    def _build(self):
        p = wx.Panel(self)
        gap = self.FromDIP(6)
        grid = wx.FlexGridSizer(cols=2, vgap=gap, hgap=self.FromDIP(10))
        grid.AddGrowableCol(1)

        def row(label, ctrl):
            grid.Add(wx.StaticText(p, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(ctrl, 1, wx.EXPAND)

        # LCSC number + load
        self.lcsc = wx.TextCtrl(p, style=wx.TE_PROCESS_ENTER)
        self.lcsc.SetHint("z. B. C20917")
        self.lcsc.Bind(wx.EVT_TEXT_ENTER, lambda e: self.on_load())
        self.load_btn = wx.Button(p, label="Laden")
        self.load_btn.Bind(wx.EVT_BUTTON, lambda e: self.on_load())
        box = wx.BoxSizer(wx.HORIZONTAL)
        box.Add(self.lcsc, 1, wx.EXPAND | wx.RIGHT, gap)
        box.Add(self.load_btn, 0)
        row("LCSC-Nummer", box)
        self.status = wx.StaticText(p, label="")
        grid.AddSpacer(0)
        grid.Add(self.status, 0, wx.EXPAND)

        # library
        self.lib_box = wx.ComboBox(p, choices=self.settings.get("libraries", []))
        self.lib_box.Bind(wx.EVT_TEXT, lambda e: self.on_library())
        self.lib_box.Bind(wx.EVT_COMBOBOX, lambda e: self.on_library())
        browse = wx.Button(p, label="Durchsuchen…")
        browse.Bind(wx.EVT_BUTTON, self.on_browse)
        box = wx.BoxSizer(wx.HORIZONTAL)
        box.Add(self.lib_box, 1, wx.EXPAND | wx.RIGHT, gap)
        box.Add(browse, 0)
        row("Library-Ordner", box)
        self.lib_info = wx.StaticText(p, label="")
        grid.AddSpacer(0)
        grid.Add(self.lib_info, 0, wx.EXPAND)
        self.model_prefix = self._text(p, "model_prefix")
        row("3D-Pfad im Footprint", self.model_prefix)

        grid.Add(wx.StaticLine(p), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, gap)
        grid.Add(wx.StaticLine(p), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, gap)

        # fields
        self.category = wx.Choice(p, choices=[""] + list(conv.CATEGORIES))
        self.category.Bind(wx.EVT_CHOICE, self.on_category)
        self.reference = wx.Choice(p, choices=[])
        self.reference.Bind(wx.EVT_CHOICE, lambda e: self.refresh_state())
        box = wx.BoxSizer(wx.HORIZONTAL)
        box.Add(self.category, 1, wx.EXPAND | wx.RIGHT, gap)
        box.Add(wx.StaticText(p, label="Reference"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, gap)
        box.Add(self.reference, 0)
        row("Kategorie", box)

        self.f = {}
        for key, label in (("symbol_name", "Symbolname"), ("value", "Value"),
                           ("description", "Description"), ("manufacturer", "Manufacturer"),
                           ("mpn", "MPN"), ("datasheet", "Datasheet"), ("fp_name", "Footprint-Name"),
                           ("jlcpcb_correction", "JLCPCB_CORRECTION")):
            self.f[key] = self._text(p, key)
            row(label, self.f[key])
        self.f["jlcpcb_correction"].SetHint("optional, nur geprüfte Werte: x;y;Drehung")
        self.fp_state = wx.StaticText(p, label="")
        grid.AddSpacer(0)
        grid.Add(self.fp_state, 0, wx.EXPAND)
        self.status_choice = wx.Choice(p, choices=conv.STATUS_VALUES)
        self.status_choice.SetSelection(0)
        row("Status", self.status_choice)

        self.notes = wx.TextCtrl(p, style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.notes.SetMinSize(self.FromDIP(wx.Size(-1, 110)))

        self.add_btn = wx.Button(p, label="Zur Library hinzufügen")
        self.add_btn.Bind(wx.EVT_BUTTON, self.on_add)
        close = wx.Button(p, wx.ID_CANCEL, "Schließen")
        close.Bind(wx.EVT_BUTTON, self.on_close)
        btns = wx.BoxSizer(wx.HORIZONTAL)
        btns.AddStretchSpacer()
        btns.Add(self.add_btn, 0, wx.RIGHT, gap)
        btns.Add(close, 0)

        top = wx.BoxSizer(wx.VERTICAL)
        m = self.FromDIP(14)
        top.Add(grid, 0, wx.EXPAND | wx.ALL, m)
        top.Add(wx.StaticText(p, label="Hinweise zur Konvention:"), 0, wx.LEFT | wx.RIGHT, m)
        top.Add(self.notes, 1, wx.EXPAND | wx.ALL, m)
        top.Add(btns, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, m)
        p.SetSizer(top)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(p, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

    # ------------------------------------------------------------- helpers
    def set(self, key, value):
        """Programmatic change (does not mark the field as hand-edited)."""
        ctrl = self.model_prefix if key == "model_prefix" else self.f[key]
        if ctrl.GetValue() != value:
            ctrl.ChangeValue(value)

    def get(self, key):
        ctrl = self.model_prefix if key == "model_prefix" else self.f[key]
        return ctrl.GetValue().strip()

    def cat(self):
        return self.category.GetStringSelection()

    def say(self, text):
        self.status.SetLabel(text)
        self.Layout()

    def set_busy(self, busy):
        self.busy = busy
        self.load_btn.Enable(not busy)
        self.refresh_state()

    # -------------------------------------------------------------- events
    def on_edit(self, name):
        if name == "mpn":  # MPN feeds the suggestions, it is not a suggestion itself
            self.apply_suggestions(force=False)
            return
        self.dirty.add(name)
        self.refresh_state()

    def on_browse(self, _e):
        dlg = wx.DirDialog(self, "Library-Ordner wählen (enthält .kicad_sym, .pretty, .3dshapes)",
                           defaultPath=self.lib_box.GetValue() or str(Path.home()))
        if dlg.ShowModal() == wx.ID_OK:
            self.lib_box.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_library(self):
        root = self.lib_box.GetValue().strip()
        if root and Path(root).is_dir():
            self.paths = lib.detect_library(root)
            p = self.paths
            self.lib_info.SetLabel("Library '%s':  %s %s  |  %s %s  |  %s %s" % (
                p.name, p.sym_file.name, "✓" if p.sym_file.is_file() else "(neu)",
                p.pretty.name, "✓" if p.pretty.is_dir() else "(neu)",
                p.shapes.name, "✓" if p.shapes.is_dir() else "(neu)"))
            saved = self.settings.get("model_prefix", {}).get(str(p.root))
            if saved:
                self.set("model_prefix", saved)
            elif "model_prefix" not in self.dirty:
                self.set("model_prefix", conv.default_model_prefix(p.root.name, p.name))
        else:
            self.paths = None
            self.lib_info.SetLabel("Ordner existiert nicht." if root else "")
        self.Layout()
        self.refresh_state()

    def on_category(self, _e):
        refs = conv.CATEGORIES.get(self.cat(), [])
        self.reference.Set(refs)
        if refs:
            self.reference.SetSelection(0)
        self.apply_suggestions(force=False)

    def on_load(self):
        if self.busy:
            return
        lcsc = lib.normalize_lcsc(self.lcsc.GetValue())
        if not lcsc:
            self.say("Bitte eine LCSC-Nummer wie C20917 eingeben.")
            return
        self.lcsc.ChangeValue(lcsc)
        self.say("Lade %s von EasyEDA …" % lcsc)
        self.set_busy(True)

        def work():
            try:
                cad, info = lib.fetch_part(lcsc)
                wx.CallAfter(self.loaded, cad, info)
            except Exception as e:  # noqa: BLE001 - shown to the user
                wx.CallAfter(self.load_failed, str(e) or repr(e))

        threading.Thread(target=work, daemon=True).start()

    def load_failed(self, msg):
        self.say(msg)
        self.set_busy(False)

    def loaded(self, cad, info):
        self.cad, self.info = cad, info
        self.dirty = {"model_prefix"} & self.dirty
        self.say("Geladen: %s" % (info.title or info.lcsc))
        guess = conv.guess_category(info.description, info.prefix)
        self.category.SetStringSelection(guess)
        refs = conv.CATEGORIES.get(guess, [])
        self.reference.Set(refs)
        if refs:
            self.reference.SetSelection(refs.index(info.prefix) if info.prefix in refs else 0)
        for key, val in (("manufacturer", info.manufacturer), ("mpn", info.mpn), ("datasheet", info.datasheet)):
            self.set(key, val)
        self.set("jlcpcb_correction", "")
        self.apply_suggestions(force=True)
        self.set_busy(False)

    def apply_suggestions(self, force):
        """Fill symbol name, value, description, footprint from the loaded part and category."""
        if not self.info:
            self.refresh_state()
            return
        cat = self.cat()
        if cat:
            value, desc = conv.suggest(cat, self.info.description, self.info.package, self.get("mpn"))
            pairs = {"symbol_name": conv.symbol_name(cat, self.get("mpn")), "value": value,
                     "description": desc, "fp_name": conv.default_footprint_name(cat, self.info.package)}
            for key, val in pairs.items():
                if force or key not in self.dirty:
                    self.set(key, val)
                    self.dirty.discard(key)
        self.refresh_state()

    def refresh_state(self):
        """Update footprint hint, convention warnings and the state of the add button."""
        fp = self.get("fp_name")
        if self.paths and fp:
            exists = self.paths.footprint_exists(fp)
            self.fp_state.SetLabel("✓ existiert in der Library: wird wiederverwendet, nichts überschrieben"
                                   if exists else "neu: wird aus den EasyEDA-Daten erzeugt (inkl. 3D-Modell)")
        else:
            self.fp_state.SetLabel("")
        form = {k: self.get(k) for k in self.f}
        form.update(category=self.cat(), lcsc=self.lcsc.GetValue().strip())
        errors, warnings = conv.check(form)
        if self.paths is None:
            errors.append("Library-Ordner wählen.")
        elif self.paths.symbol_exists(form["symbol_name"]):
            errors.append("Symbol existiert bereits in der Library.")
        if self.cad is None:
            errors.append("Erst eine LCSC-Nummer laden.")
        lines = ["FEHLER: " + e for e in errors] + ["Hinweis: " + w for w in warnings]
        self.notes.ChangeValue("\n".join(lines) if lines else "Keine Auffälligkeiten.")
        self.add_btn.Enable(not errors and not self.busy)
        self.Layout()

    def on_add(self, _e):
        if self.busy or self.paths is None or self.cad is None:
            return
        form = lib.PartForm(
            lcsc=self.lcsc.GetValue().strip(), category=self.cat(),
            reference=self.reference.GetStringSelection(), symbol_name=self.get("symbol_name"),
            value=self.get("value"), description=self.get("description"),
            manufacturer=self.get("manufacturer"), mpn=self.get("mpn"), datasheet=self.get("datasheet"),
            fp_name=self.get("fp_name"), status=self.status_choice.GetStringSelection(),
            jlcpcb_correction=self.get("jlcpcb_correction"))
        paths, prefix, cad = self.paths, self.get("model_prefix"), self.cad
        self.remember_library(paths, prefix)
        self.say("Schreibe in die Library …")
        self.set_busy(True)

        def work():
            try:
                res = lib.import_part(cad, form, paths, prefix)
                wx.CallAfter(self.added, form, res)
            except Exception as e:  # noqa: BLE001 - shown to the user
                wx.CallAfter(self.add_failed, str(e) or repr(e), traceback.format_exc())

        threading.Thread(target=work, daemon=True).start()

    def add_failed(self, msg, tb):
        self.say("Fehler beim Schreiben.")
        self.set_busy(False)
        wx.MessageBox(msg, "LCSC Importer", wx.OK | wx.ICON_ERROR, self)

    def added(self, form, res):
        self.say("Fertig: %s hinzugefügt." % form.symbol_name)
        wx.MessageBox("\n".join(res.messages) + "\n\nIn KiCad ggf. die Symbolbibliothek neu laden "
                      "(Symbol-Editor) bzw. KiCad neu starten.", "LCSC Importer",
                      wx.OK | wx.ICON_INFORMATION, self)
        self.cad = self.info = None
        self.dirty = set()
        self.lcsc.ChangeValue("")
        for k in self.f:
            self.set(k, "")
        self.category.SetSelection(0)
        self.reference.Set([])
        self.set_busy(False)
        self.lcsc.SetFocus()

    def remember_library(self, paths, prefix):
        s = self.settings
        root = str(paths.root)
        libs = [root] + [x for x in s.get("libraries", []) if x != root]
        s["libraries"] = libs[:MAX_RECENT_LIBS]
        s["last_library"] = root
        s.setdefault("model_prefix", {})[root] = prefix
        lib.save_settings(s)

    def on_close(self, _e):
        if self.paths is not None:
            self.remember_library(self.paths, self.get("model_prefix"))
        self.Destroy()


def main():
    app = wx.App(False)
    dlg = ImporterDialog()
    dlg.Show()
    dlg.Raise()
    app.MainLoop()
