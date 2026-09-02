"""Module entry point so ``python -m cannonball_map`` runs the CLI.

Windows Smart App Control blocks freshly generated, unsigned console-script
launchers such as ``.venv/Scripts/cannonball-map.exe`` (WinError 4551), the
same way it rejected the pytest launcher on 2026-07-30. Invoking the package
through the signed interpreter avoids the launcher entirely on every platform.
"""

from cannonball_map.cli import app

if __name__ == "__main__":
    app()
