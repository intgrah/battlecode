import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "cambc.toml"


@dataclass
class CambcConfig:
    bots_dir: str = "bots"
    maps_dir: str = "maps"
    replay: str = "replay.replay26"
    seed: int = 1


def find_config() -> tuple[CambcConfig, Path]:
    """Walk up from cwd to find cambc.toml. Returns (config, project_root)."""
    cwd = Path.cwd().resolve()
    for directory in [cwd] + list(cwd.parents):
        config_path = directory / CONFIG_FILENAME
        if config_path.is_file():
            raw = config_path.read_bytes()
            try:
                data = tomllib.loads(raw.decode("utf-8"))
            except UnicodeDecodeError:
                # Fix files written with system encoding (e.g. cp1252 on Windows)
                data = tomllib.loads(raw.decode("utf-8", errors="replace"))
                config_path.write_bytes(raw.decode("utf-8", errors="replace").encode("utf-8"))
            return _parse_config(data), directory
    return CambcConfig(), cwd


def _parse_config(data: dict) -> CambcConfig:
    return CambcConfig(
        bots_dir=data.get("bots_dir", CambcConfig.bots_dir),
        maps_dir=data.get("maps_dir", CambcConfig.maps_dir),
        replay=data.get("replay", CambcConfig.replay),
        seed=data.get("seed", CambcConfig.seed),
    )
