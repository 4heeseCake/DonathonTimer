"""Entry point compatible with PyInstaller's windowed/no-console mode."""
import os
import sys

# Windows GUI executables don't have console streams. Avoid third-party
# code crashing when it probes sys.stderr.isatty() or writes diagnostics.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from src.donathon.application import run

if __name__ == "__main__":
    run()
