"""
Makes the research pipeline's own bare-style imports (`from engine...`,
`from signals...`, `from strategies...` -- used throughout signals/,
strategies/, and this tests/ directory) resolve correctly regardless of
whether pytest is invoked from the repo root or from inside
research/xauusd_scalping/ itself.

Found 2026-09-22: test_engine.py (P2) uses the fully-qualified
`research.xauusd_scalping.engine...` style and already worked fine from
the repo root; test_signals.py and every strategies/*.py module (P3) were
written with bare imports, which only resolve when this directory's own
path is on sys.path -- true when a script is run directly from within
research/xauusd_scalping/ (Python adds the script's own directory
automatically), false under pytest's rootdir-based resolution from the
repo root. Adding this directory to sys.path here lets both import styles
coexist without touching the already-written strategy files.
"""

import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).parent.parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))
