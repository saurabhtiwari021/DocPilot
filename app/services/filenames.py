"""
Filename sanitization.

`UploadFile.filename` is attacker-controlled input - a client can send
literally anything, including "../../etc/passwd" or a Windows-style
"..\\..\\something.txt". Every place that does
`os.path.join(some_base_dir, user_id, filename)` is a potential path
traversal out of that user's directory (and, since the same filename is
reused to build the S3 key, out of their prefix in the bucket too).

`safe_filename()` is the single place that turns an untrusted filename
into something safe to join onto a base directory: it keeps only the
basename (stripping any directory components a traversal payload would
rely on) and falls back to a generated name if nothing usable is left.
"""

import re
import uuid
from pathlib import Path

# Conservative allow-list: letters, digits, dot, dash, underscore, space.
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]")


def safe_filename(raw_filename: str) -> str:
    """
    Return a filename safe to join onto a per-user base directory.

    - Strips any directory components (defeats "../" and "..\\" traversal
      and absolute paths), keeping only the final path segment.
    - Strips characters outside a conservative allow-list.
    - Falls back to a random name if nothing usable remains (e.g. the
      original filename was empty, only dots, or entirely special chars).
    """
    # Path(...).name collapses "../../etc/passwd" -> "passwd" and also
    # handles Windows-style separators and absolute paths.
    candidate = Path((raw_filename or "").strip().replace("\\", "/")).name
    candidate = _UNSAFE_CHARS.sub("_", candidate).strip(" .")

    if not candidate:
        return uuid.uuid4().hex

    return candidate
