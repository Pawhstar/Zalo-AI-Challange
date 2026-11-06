"""Make stdout/stderr safe for Vietnamese text on consoles that are not UTF-8.

Windows consoles often default to cp1252, where printing a shop file name like
"danh sách hàng hóa" raises UnicodeEncodeError and kills the script. Reconfiguring
the streams to UTF-8 (with errors="replace" as a last resort) keeps the output
readable and never fatal.
"""
import sys


def setup_io():
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
