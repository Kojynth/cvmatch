#!/usr/bin/env python3
"""Run the versioned contract suite."""

from __future__ import annotations

import subprocess
import sys


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", "tests/contracts", "-q"])
    )
