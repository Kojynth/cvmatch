#!/usr/bin/env python3
"""Run the versioned mass-apply suite."""

from __future__ import annotations

import subprocess
import sys


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", "tests/mass_apply", "-q"])
    )
