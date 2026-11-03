"""Scrawl: a tiny, fast notepad for brain dumps and to-do lists.

Required permissions: none. Scrawl runs as the signed-in user, reads and
writes only its notes folder and its own config folder, listens only on the
loopback interface, and (optionally) writes one value under
``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` for start-at-login.
"""

__version__ = "0.1.0"
