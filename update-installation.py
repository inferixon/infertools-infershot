"""Update an installed copy while adding only missing configuration keys."""

import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


FILES = ("infershot.py", "runtime_state.py", "run-infershot.bat", "stop-infershot.ps1",
         "update-installation.py", "requirements.txt")


def append_defaults(existing, defaults):
    result = copy.deepcopy(existing)
    for key, value in defaults.items():
        if key not in result:
            result[key] = copy.deepcopy(value)
        elif isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = append_defaults(result[key], value)
    return result


def atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def install(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError("Choose an installed directory distinct from the source repository")
    defaults = json.loads((source / "config.json").read_text(encoding="utf-8-sig"))
    config_path = target / "config.json"
    existing = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    if not isinstance(existing, dict) or not isinstance(defaults, dict):
        raise ValueError("Configuration must be a JSON object")
    merged = append_defaults(existing, defaults)
    payload = {name: (source / name).read_bytes() for name in FILES}
    if not config_path.exists() or merged != existing:
        payload["config.json"] = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    changes = {name: data for name, data in payload.items()
               if not (target / name).exists() or (target / name).read_bytes() != data}
    target.mkdir(parents=True, exist_ok=True)
    backup = None
    if changes:
        backup = Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime("%Y%m%d-%H%M%S-"),
                                       dir=str(_backup_root(target))))
        for name in changes:
            if (target / name).exists():
                shutil.copy2(target / name, backup / name)
        for name, data in changes.items():
            atomic_write(target / name, data)
    installed = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if append_defaults(existing, installed) != installed:
        raise RuntimeError("Existing configuration values were changed")
    hashes = {}
    for name in FILES:
        expected = hashlib.sha256(payload[name]).hexdigest()
        hashes[name] = hashlib.sha256((target / name).read_bytes()).hexdigest()
        if hashes[name] != expected:
            raise RuntimeError(f"Installed code hash mismatch: {name}")
    return {"target": str(target), "changed": sorted(changes), "backup": str(backup) if backup else None,
            "sha256": hashes["infershot.py"], "files_sha256": hashes, "settings_preserved": True}


def _backup_root(target):
    directory = target / ".updates"
    directory.mkdir(exist_ok=True)
    return directory


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(install(Path(__file__).parent, args.target), indent=2))
