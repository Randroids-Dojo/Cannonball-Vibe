from __future__ import annotations

import os
import stat
import sys
import zipfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: archive.py SOURCE_DIR ROOT_NAME OUTPUT.zip")
    source = Path(sys.argv[1]).resolve()
    root_name = sys.argv[2]
    output = Path(sys.argv[3]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            if path.is_symlink():
                raise SystemExit(f"package archives must not contain symlinks: {path}")
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(f"{root_name}/{relative}", timestamp)
            info.create_system = 3
            mode = path.stat().st_mode & 0o777
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, path.read_bytes())
    os.utime(output, (315532800, 315532800))


if __name__ == "__main__":
    main()
