"""Plugin action entrypoint: opens the LCSC importer dialog."""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import dialog

    dialog.main()
except Exception:  # shown by KiCad as plugin error, and kept in a log file
    text = traceback.format_exc()
    try:
        with open(os.path.join(tempfile.gettempdir(), "kicad_lcsc_importer.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
    sys.exit(text)
