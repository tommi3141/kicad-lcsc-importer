# KiCad LCSC Importer

KiCad-Plugin (Windows, KiCad 9/10): Bauteil per LCSC-Nummer in eine Library importieren, nach den
EDENLibrary-Konventionen. Ein Dialog legt Symbol, Footprint und 3D-Modell an.

## Installation

1. `install.bat` doppelklicken. Es kopiert `lcsc-importer` nach `Dokumente\KiCad\<Version>\plugins\`.
2. In KiCad: Einstellungen › Plugins › **KiCad-API aktivieren**. KiCad neu starten.
3. Beim ersten Start installiert KiCad per pip das Paket `easyeda2kicad` in die Plugin-Umgebung (Internet nötig).
4. Button **LCSC Importer** in der Werkzeugleiste des Schaltplan- oder PCB-Editors klicken.

## Der Dialog

1. LCSC-Nummer eingeben (`C20917`), **Laden**. Die Daten kommen von EasyEDA, die Umwandlung in KiCad-Formate
   übernimmt [easyeda2kicad](https://github.com/uPesy/easyeda2kicad.py).
2. **Library-Ordner** wählen (Ordner mit `<Name>.kicad_sym`, `<Name>.pretty`, `<Name>.3dshapes`).
   Der 3D-Pfad im Footprint ist vorbelegt als `${KIPRJMOD}/libs/<ordner>/<Name>.3dshapes`.
3. Kategorie, Symbolname (`<kategorie>/<MPN>`), Value, Description, Hersteller, Footprint-Name usw. sind aus den
   LCSC-Daten vorbelegt und nach den Konventionen aufgebaut (RKM-Werte, Description-Schema, Felder `MPN`, `LCSC`,
   `Status`, `ki_fp_filters`, …). Alles ist editierbar, das Feld „Hinweise“ warnt bei Abweichungen.
4. **Zur Library hinzufügen** schreibt Symbol, Footprint und STEP-Modell (`<Footprint-Name>.step`).

Beim Schreiben werden bestehende Symbole nie überschrieben. Existiert der Footprint schon, wird er samt
3D-Modell wiederverwendet und nicht verändert. Das Symbol wird so formatiert, wie KiCad 10 es speichert (kleine
Git-Diffs). Neue Footprints werden, falls `kicad-cli` gefunden wird, ins aktuelle Dateiformat konvertiert.

## Grenzen

- Value und Description sind Vorschläge aus der LCSC-Produktbeschreibung. Vollständig automatisch gelingen sie für
  Widerstände, Kondensatoren, Induktivitäten/Ferrite, Sicherungen, Quarze und teilweise LEDs. Bei den anderen
  Kategorien liefert der Dialog nur das Gerüst (`KLASSE | Hinweistext | Gehäuse`), die Kennwerte ergänzt du.
- `easyeda2kicad` setzt das 3D-Modell ohne Offset. Lage und Drehung bitte im 3D-Viewer prüfen.
- Einstellungen: `~/.kicad_lcsc_importer.json`, Fehler: `%TEMP%\kicad_lcsc_importer.log`.

## Tests

`pip install easyeda2kicad==1.0.1 && python tests/test_importer.py` (offline, mit simulierten Daten).

## Struktur

```
lcsc-importer/   das KiCad-Plugin (plugin.json, Dialog, Konventionen, Library-Schreiber)
tests/           Offline-Tests
install.bat      kopiert das Plugin nach Dokumente\KiCad\<Version>\plugins
edenlibrary/     optional: lokale Kopie der Library zum Testen (nicht im Git)
```

## Lizenz

MIT, siehe `LICENSE`. `easyeda2kicad` (AGPL-3.0) wird nicht mitgeliefert, sondern per pip installiert.
