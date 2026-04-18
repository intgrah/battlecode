"""AST-based bot obfuscator.

Renames every user-defined module, class, function, and local/global
identifier to opaque short names. Strips comments and docstrings. Preserves
the cambc API surface, the `Player` class and its `run`/`__init__` methods,
dunders, and anything used via getattr/string imports (best-effort).

Usage:
    uv run python scripts/obfuscate.py <bot_path> [--out <dir>]

If --out is omitted, writes to <bot_path>-obf/ alongside the source.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import keyword
import re
import shutil
import string
import sys
from pathlib import Path


def _builtin_method_names() -> frozenset[str]:
    import collections
    import io

    types: list[type] = [
        list,
        dict,
        set,
        frozenset,
        tuple,
        str,
        bytes,
        bytearray,
        int,
        float,
        complex,
        bool,
        range,
        slice,
        type,
        object,
        Exception,
        BaseException,
        memoryview,
        io.IOBase,
        io.TextIOBase,
        io.BufferedIOBase,
        io.BytesIO,
        io.StringIO,
        collections.deque,
        collections.OrderedDict,
        collections.defaultdict,
        collections.Counter,
        collections.ChainMap,
    ]
    names: set[str] = set()
    for t in types:
        names.update(n for n in dir(t) if not n.startswith("_"))
    return frozenset(names)


BUILTIN_METHOD_NAMES: frozenset[str] = _builtin_method_names()


CAMBC_NAMES: frozenset[str] = frozenset(
    {
        "cambc",
        "Controller",
        "Direction",
        "EntityType",
        "Environment",
        "GameConstants",
        "GameError",
        "Position",
        "ResourceType",
        "Team",
    }
)

CAMBC_ENUM_MEMBERS: frozenset[str] = frozenset(
    {
        "A",
        "B",
        "TITANIUM",
        "RAW_AXIONITE",
        "REFINED_AXIONITE",
        "BUILDER_BOT",
        "CORE",
        "GUNNER",
        "SENTINEL",
        "BREACH",
        "LAUNCHER",
        "CONVEYOR",
        "SPLITTER",
        "ARMOURED_CONVEYOR",
        "BRIDGE",
        "HARVESTER",
        "FOUNDRY",
        "ROAD",
        "BARRIER",
        "MARKER",
        "EMPTY",
        "WALL",
        "ORE_TITANIUM",
        "ORE_AXIONITE",
        "NORTH",
        "NORTHEAST",
        "EAST",
        "SOUTHEAST",
        "SOUTH",
        "SOUTHWEST",
        "WEST",
        "NORTHWEST",
        "CENTRE",
    }
)

CAMBC_GAME_CONSTANTS: frozenset[str] = frozenset(
    {
        "MAX_TURNS",
        "STACK_SIZE",
        "STARTING_TITANIUM",
        "STARTING_AXIONITE",
        "MAX_TEAM_UNITS",
        "PASSIVE_TITANIUM_AMOUNT",
        "PASSIVE_TITANIUM_INTERVAL",
        "AXIONITE_CONVERSION_TITANIUM_RATE",
        "ACTION_RADIUS_SQ",
        "CORE_SPAWNING_RADIUS_SQ",
        "CORE_ACTION_RADIUS_SQ",
        "BRIDGE_TARGET_RADIUS_SQ",
        "CORE_VISION_RADIUS_SQ",
        "BUILDER_BOT_VISION_RADIUS_SQ",
        "GUNNER_VISION_RADIUS_SQ",
        "SENTINEL_VISION_RADIUS_SQ",
        "BREACH_VISION_RADIUS_SQ",
        "LAUNCHER_VISION_RADIUS_SQ",
        "CONVEYOR_BASE_COST",
        "SPLITTER_BASE_COST",
        "BRIDGE_BASE_COST",
        "ARMOURED_CONVEYOR_BASE_COST",
        "HARVESTER_BASE_COST",
        "ROAD_BASE_COST",
        "BARRIER_BASE_COST",
        "GUNNER_BASE_COST",
        "SENTINEL_BASE_COST",
        "BREACH_BASE_COST",
        "LAUNCHER_BASE_COST",
        "FOUNDRY_BASE_COST",
        "BUILDER_BOT_BASE_COST",
        "GUNNER_ROTATE_COST",
        "GUNNER_ROTATE_COOLDOWN",
        "CONVEYOR_MAX_HP",
        "SPLITTER_MAX_HP",
        "BRIDGE_MAX_HP",
        "ARMOURED_CONVEYOR_MAX_HP",
        "HARVESTER_MAX_HP",
        "ROAD_MAX_HP",
        "BARRIER_MAX_HP",
        "FOUNDRY_MAX_HP",
        "MARKER_MAX_HP",
        "BUILDER_BOT_MAX_HP",
        "CORE_MAX_HP",
        "GUNNER_MAX_HP",
        "SENTINEL_MAX_HP",
        "BREACH_MAX_HP",
        "LAUNCHER_MAX_HP",
        "BUILDER_BOT_SELF_DESTRUCT_DAMAGE",
        "BUILDER_BOT_ATTACK_DAMAGE",
        "BUILDER_BOT_ATTACK_COST",
        "BUILDER_BOT_HEAL_COST",
        "HEAL_AMOUNT",
        "GUNNER_DAMAGE",
        "GUNNER_AXIONITE_DAMAGE",
        "GUNNER_FIRE_COOLDOWN",
        "GUNNER_AMMO_COST",
        "SENTINEL_DAMAGE",
        "SENTINEL_FIRE_COOLDOWN",
        "SENTINEL_AMMO_COST",
        "SENTINEL_STUN_DURATION",
        "BREACH_DAMAGE",
        "BREACH_SPLASH_DAMAGE",
        "BREACH_FIRE_COOLDOWN",
        "BREACH_AMMO_COST",
        "BREACH_ATTACK_RADIUS_SQ",
        "LAUNCHER_FIRE_COOLDOWN",
    }
)

CAMBC_METHODS: frozenset[str] = frozenset(
    {
        "add",
        "build",
        "build_armoured_conveyor",
        "build_barrier",
        "build_breach",
        "build_bridge",
        "build_conveyor",
        "build_foundry",
        "build_gunner",
        "build_harvester",
        "build_launcher",
        "build_road",
        "build_sentinel",
        "build_splitter",
        "can_build",
        "can_build_armoured_conveyor",
        "can_build_barrier",
        "can_build_breach",
        "can_build_bridge",
        "can_build_conveyor",
        "can_build_foundry",
        "can_build_gunner",
        "can_build_harvester",
        "can_build_launcher",
        "can_build_road",
        "can_build_sentinel",
        "can_build_splitter",
        "can_destroy",
        "can_fire",
        "can_fire_from",
        "can_heal",
        "can_launch",
        "can_move",
        "can_place_marker",
        "can_rotate",
        "can_spawn",
        "convert",
        "delta",
        "destroy",
        "direction_to",
        "distance_squared",
        "draw_indicator_dot",
        "draw_indicator_line",
        "fire",
        "get_action_cooldown",
        "get_ammo_amount",
        "get_ammo_type",
        "get_armoured_conveyor_cost",
        "get_attackable_tiles",
        "get_attackable_tiles_from",
        "get_barrier_cost",
        "get_breach_cost",
        "get_bridge_cost",
        "get_bridge_target",
        "get_builder_bot_cost",
        "get_conveyor_cost",
        "get_cpu_time_elapsed",
        "get_current_round",
        "get_direction",
        "get_entity_type",
        "get_foundry_cost",
        "get_global_resources",
        "get_gunner_cost",
        "get_gunner_target",
        "get_harvester_cost",
        "get_hp",
        "get_id",
        "get_launcher_cost",
        "get_map_height",
        "get_map_width",
        "get_marker_value",
        "get_max_hp",
        "get_move_cooldown",
        "get_nearby_buildings",
        "get_nearby_entities",
        "get_nearby_tiles",
        "get_nearby_units",
        "get_position",
        "get_road_cost",
        "get_scale_percent",
        "get_sentinel_cost",
        "get_splitter_cost",
        "get_stored_resource",
        "get_stored_resource_id",
        "get_team",
        "get_tile_builder_bot_id",
        "get_tile_building_id",
        "get_tile_env",
        "get_unit_count",
        "get_vision_radius_sq",
        "heal",
        "is_in_vision",
        "is_tile_empty",
        "is_tile_passable",
        "launch",
        "move",
        "opposite",
        "place_marker",
        "resign",
        "rotate",
        "rotate_left",
        "rotate_right",
        "self_destruct",
        "spawn_builder",
        "x",
        "y",
    }
)

PRESERVED_NAMES: frozenset[str] = (
    CAMBC_NAMES
    | CAMBC_ENUM_MEMBERS
    | CAMBC_GAME_CONSTANTS
    | CAMBC_METHODS
    | BUILTIN_METHOD_NAMES
    | frozenset(dir(builtins))
    | frozenset(keyword.kwlist)
    | frozenset(keyword.softkwlist)
    | frozenset(
        {
            "Player",
            "run",
            "__init__",
            "annotations",
            "__future__",
            "TYPE_CHECKING",
            "typing",
            "sys",
            "os",
            "math",
            "random",
            "heapq",
            "collections",
            "itertools",
            "functools",
            "dataclasses",
            "enum",
            "abc",
            "time",
            "io",
            "traceback",
            "copy",
            "bisect",
            "array",
            "operator",
            "struct",
            "string",
            "re",
            "json",
            "pickle",
            "hashlib",
            "typing_extensions",
        }
    )
)


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


class NameGen:
    def __init__(self, reserved: frozenset[str]) -> None:
        self._reserved = set(reserved) | set(keyword.kwlist) | set(keyword.softkwlist)
        self._used: set[str] = set()
        self._i = 0

    def fresh(self) -> str:
        alphabet = string.ascii_lowercase
        while True:
            n = self._i
            self._i += 1
            chars: list[str] = []
            n += 1
            while n > 0:
                n -= 1
                chars.append(alphabet[n % 26])
                n //= 26
            name = "".join(reversed(chars))
            if name in self._reserved or name in self._used:
                continue
            self._used.add(name)
            return name


def collect_py_files(root: Path) -> list[Path]:
    return [
        p
        for p in sorted(root.rglob("*.py"))
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    ]


def module_path_from(root: Path, file: Path) -> tuple[str, ...]:
    rel = file.relative_to(root)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return tuple(parts)


def parse_all(files: list[Path]) -> dict[Path, ast.Module]:
    out: dict[Path, ast.Module] = {}
    for f in files:
        out[f] = ast.parse(f.read_text(), filename=str(f))
    return out


def collect_local_modules(
    root: Path, files: list[Path]
) -> dict[tuple[str, ...], Path]:
    mods: dict[tuple[str, ...], Path] = {}
    for f in files:
        parts = module_path_from(root, f)
        if parts:
            mods[parts] = f
    return mods


def is_local_module(mod: str, local_modules: dict[tuple[str, ...], Path]) -> bool:
    parts = tuple(mod.split("."))
    for i in range(1, len(parts) + 1):
        if parts[:i] in local_modules:
            return True
    return False


def collect_stdlib_attrs(
    trees: dict[Path, ast.Module],
    local_modules: dict[tuple[str, ...], Path],
) -> set[str]:
    """Preserve attributes owned by external (non-local) modules.

    Strategy: for every `from stdlib_mod import X` or `import stdlib_mod`,
    dynamically import the module, walk every public attribute it exposes,
    and record their public attribute/method names. This captures cases
    like `self.rng = Random(...); self.rng.choice(...)` where `choice`
    would otherwise be renamed — `Random` was imported from `random`, so
    every public method of `random.Random` (and every other thing in
    `random`) is preserved.
    """
    import importlib

    preserved: set[str] = set()
    modules_to_scan: set[str] = set()
    imported_names: dict[str, str] = {}  # name-as-bound -> module

    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if is_local_module(a.name, local_modules):
                        continue
                    modules_to_scan.add(a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and not is_local_module(node.module, local_modules):
                    modules_to_scan.add(node.module)
                    for a in node.names:
                        if a.name == "*":
                            continue
                        preserved.add(a.name)
                        imported_names[a.asname or a.name] = node.module

    def _collect_from(obj: object, depth: int) -> None:
        if depth <= 0:
            return
        try:
            attrs = dir(obj)
        except Exception:
            return
        for a in attrs:
            if a.startswith("_"):
                continue
            preserved.add(a)
            if depth > 1:
                try:
                    sub = getattr(obj, a)
                except Exception:
                    continue
                if isinstance(sub, type):
                    _collect_from(sub, depth - 1)

    for mod_name in sorted(modules_to_scan):
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        _collect_from(mod, depth=2)

    return preserved


def collect_names(
    trees: dict[Path, ast.Module],
    local_modules: dict[tuple[str, ...], Path],
) -> set[str]:
    names: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            if not is_dunder(node.name):
                names.add(node.name)
            for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                names.add(a.arg)
            if node.args.vararg:
                names.add(node.args.vararg.arg)
            if node.args.kwarg:
                names.add(node.args.kwarg.arg)
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.visit_FunctionDef(node)  # type: ignore[arg-type]

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            if not is_dunder(node.name):
                names.add(node.name)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if not is_dunder(node.id):
                names.add(node.id)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if not is_dunder(node.attr):
                names.add(node.attr)
            self.generic_visit(node)

        def visit_arg(self, node: ast.arg) -> None:
            names.add(node.arg)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module and is_local_module(node.module, local_modules):
                for a in node.names:
                    if a.name != "*":
                        names.add(a.name)
                        if a.asname:
                            names.add(a.asname)
            else:
                for a in node.names:
                    if a.asname:
                        names.add(a.asname)

        def visit_Import(self, node: ast.Import) -> None:
            for a in node.names:
                if a.asname:
                    names.add(a.asname)
                    continue
                parts = a.name.split(".")
                if is_local_module(a.name, local_modules):
                    names.add(parts[0])

    v = Visitor()
    for tree in trees.values():
        v.visit(tree)
    return names


def build_rename_map(
    all_names: set[str],
    local_modules: dict[tuple[str, ...], Path],
    extra_preserved: frozenset[str],
) -> tuple[dict[str, str], dict[tuple[str, ...], tuple[str, ...]]]:
    preserved = PRESERVED_NAMES | extra_preserved
    gen = NameGen(preserved)
    rename: dict[str, str] = {}

    # Rename package/module segments first so we can reuse their short names.
    segment_set: set[str] = set()
    for parts in local_modules:
        segment_set.update(parts)
    for seg in sorted(segment_set):
        if seg in preserved:
            continue
        rename[seg] = gen.fresh()

    for name in sorted(all_names):
        if name in rename:
            continue
        if name in preserved:
            continue
        if is_dunder(name):
            continue
        # Skip things that look like string literals (we already restrict to
        # identifier-shaped names by construction, but be paranoid).
        if not name.isidentifier():
            continue
        rename[name] = gen.fresh()

    mod_rename: dict[tuple[str, ...], tuple[str, ...]] = {}
    for parts in local_modules:
        new_parts = tuple(rename.get(p, p) for p in parts)
        mod_rename[parts] = new_parts

    return rename, mod_rename


def rename_dotted(
    mod: str,
    rename: dict[str, str],
    local_modules: dict[tuple[str, ...], Path],
) -> str:
    parts = mod.split(".")
    if not is_local_module(mod, local_modules):
        return mod
    new = [rename.get(p, p) for p in parts]
    return ".".join(new)


class Rewriter(ast.NodeTransformer):
    def __init__(
        self,
        rename: dict[str, str],
        local_modules: dict[tuple[str, ...], Path],
    ) -> None:
        self.rename = rename
        self.local_modules = local_modules

    def _r(self, name: str) -> str:
        return self.rename.get(name, name)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if not is_dunder(node.id):
            node.id = self._r(node.id)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        self.generic_visit(node)
        if not is_dunder(node.attr):
            node.attr = self._r(node.attr)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = self._r(node.arg)
        if node.annotation is not None:
            node.annotation = self.visit(node.annotation)  # type: ignore[assignment]
        return node

    def _rename_args(self, args: ast.arguments) -> None:
        for a in args.args + args.kwonlyargs + args.posonlyargs:
            a.arg = self._r(a.arg)
            if a.annotation is not None:
                a.annotation = self.visit(a.annotation)  # type: ignore[assignment]
        if args.vararg:
            args.vararg.arg = self._r(args.vararg.arg)
            if args.vararg.annotation is not None:
                args.vararg.annotation = self.visit(args.vararg.annotation)  # type: ignore[assignment]
        if args.kwarg:
            args.kwarg.arg = self._r(args.kwarg.arg)
            if args.kwarg.annotation is not None:
                args.kwarg.annotation = self.visit(args.kwarg.annotation)  # type: ignore[assignment]
        args.defaults = [self.visit(d) for d in args.defaults]  # type: ignore[assignment]
        args.kw_defaults = [  # type: ignore[assignment]
            self.visit(d) if d is not None else None for d in args.kw_defaults
        ]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if not is_dunder(node.name):
            node.name = self._r(node.name)
        self._rename_args(node.args)
        node.decorator_list = [self.visit(d) for d in node.decorator_list]  # type: ignore[assignment]
        if node.returns is not None:
            node.returns = self.visit(node.returns)  # type: ignore[assignment]
        node.body = [self.visit(s) for s in node.body]  # type: ignore[assignment]
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        return self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if not is_dunder(node.name):
            node.name = self._r(node.name)
        node.bases = [self.visit(b) for b in node.bases]  # type: ignore[assignment]
        node.keywords = [self.visit(k) for k in node.keywords]  # type: ignore[assignment]
        node.decorator_list = [self.visit(d) for d in node.decorator_list]  # type: ignore[assignment]
        node.body = [self.visit(s) for s in node.body]  # type: ignore[assignment]
        return node

    def visit_Global(self, node: ast.Global) -> ast.AST:
        node.names = [self._r(n) for n in node.names]
        return node

    def visit_Nonlocal(self, node: ast.Nonlocal) -> ast.AST:
        node.names = [self._r(n) for n in node.names]
        return node

    def visit_Import(self, node: ast.Import) -> ast.AST:
        new_names: list[ast.alias] = []
        for a in node.names:
            if is_local_module(a.name, self.local_modules):
                new_full = rename_dotted(a.name, self.rename, self.local_modules)
                asname = self._r(a.asname) if a.asname else None
                new_names.append(ast.alias(name=new_full, asname=asname))
            else:
                asname = self._r(a.asname) if a.asname else None
                new_names.append(ast.alias(name=a.name, asname=asname))
        node.names = new_names
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST:
        if node.module and is_local_module(node.module, self.local_modules):
            node.module = rename_dotted(
                node.module, self.rename, self.local_modules
            )
            new_names: list[ast.alias] = []
            for a in node.names:
                if a.name == "*":
                    new_names.append(a)
                    continue
                new_name = self._r(a.name)
                new_asname = self._r(a.asname) if a.asname else None
                new_names.append(ast.alias(name=new_name, asname=new_asname))
            node.names = new_names
        else:
            new_names = []
            for a in node.names:
                asname = self._r(a.asname) if a.asname else None
                new_names.append(ast.alias(name=a.name, asname=asname))
            node.names = new_names
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.AST:
        # Do not rename keyword argument names. We can't tell whether the
        # callee is a local (renamed) function or stdlib (e.g. sorted(...,
        # key=...)). Leaving kwargs as-is is safe for stdlib; it only fails
        # if the user calls their own renamed function by keyword — which
        # requires the parameter names on that function to stay unchanged
        # too, handled separately.
        if node.value is not None:
            node.value = self.visit(node.value)  # type: ignore[assignment]
        return node


def strip_type_imports(tree: ast.Module) -> None:
    """Drop `from __future__ import annotations`, `from typing import ...`,
    and `if TYPE_CHECKING:` blocks (they only housed annotations)."""

    def is_type_checking(node: ast.AST) -> bool:
        if isinstance(node, ast.Name) and node.id == "TYPE_CHECKING":
            return True
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "typing"
            and node.attr == "TYPE_CHECKING"
        ):
            return True
        return False

    # typing exposes runtime decorators/helpers (override, dataclass_transform,
    # final, runtime_checkable, cast, ...) so we can't blanket-drop it. Only
    # strip names that exist solely for annotations.
    TYPING_ANNOTATION_ONLY = {
        "TYPE_CHECKING",
        "Any",
        "Optional",
        "Union",
        "List",
        "Dict",
        "Tuple",
        "Set",
        "FrozenSet",
        "Type",
        "Callable",
        "Iterable",
        "Iterator",
        "Mapping",
        "MutableMapping",
        "Sequence",
        "MutableSequence",
        "Generator",
        "AsyncGenerator",
        "Awaitable",
        "Coroutine",
        "ClassVar",
        "Final",
        "Literal",
        "Annotated",
        "TypeAlias",
        "TypeGuard",
        "Never",
        "NoReturn",
        "Self",
        "LiteralString",
        "Concatenate",
        "Unpack",
    }

    class Dropper(ast.NodeTransformer):
        def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST | None:
            if node.module == "__future__":
                remaining = [a for a in node.names if a.name != "annotations"]
                if not remaining:
                    return None
                node.names = remaining
                return node
            if node.module in ("typing", "typing_extensions"):
                remaining = [
                    a for a in node.names if a.name not in TYPING_ANNOTATION_ONLY
                ]
                if not remaining:
                    return None
                node.names = remaining
                return node
            if node.module == "collections.abc":
                return None
            return node

        def visit_If(self, node: ast.If) -> ast.AST | None:
            if is_type_checking(node.test):
                if node.orelse:
                    new_body = [self.visit(s) for s in node.orelse]
                    node.body = [s for s in new_body if s is not None]  # type: ignore[misc]
                    node.orelse = []
                    node.test = ast.Constant(value=True)
                    return node
                return None
            self.generic_visit(node)
            return node

    Dropper().visit(tree)


def strip_annotations(tree: ast.Module) -> None:
    class AnnStripper(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            node.returns = None
            self._clear_args(node.args)
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            node.returns = None
            self._clear_args(node.args)
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            self.generic_visit(node)
            if not node.body:
                node.body = [ast.Pass()]
            return node

        def _clear_args(self, args: ast.arguments) -> None:
            for a in args.args + args.kwonlyargs + args.posonlyargs:
                a.annotation = None
            if args.vararg:
                args.vararg.annotation = None
            if args.kwarg:
                args.kwarg.annotation = None

        def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:
            # Always keep as AnnAssign with dummy annotation — dataclass
            # fields require annotations (with or without defaults), and we
            # can't statically detect dataclass context.
            node.annotation = ast.Name(id="int", ctx=ast.Load())
            return node

    AnnStripper().visit(tree)


def strip_docstrings(tree: ast.Module) -> None:
    class DocStripper(ast.NodeTransformer):
        def _strip_body(self, body: list[ast.stmt]) -> list[ast.stmt]:
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            return body or [ast.Pass()]

        def visit_Module(self, node: ast.Module) -> ast.AST:
            node.body = self._strip_body(node.body)
            self.generic_visit(node)
            return node

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            node.body = self._strip_body(node.body)
            self.generic_visit(node)
            return node

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
            node.body = self._strip_body(node.body)
            self.generic_visit(node)
            return node

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            node.body = self._strip_body(node.body)
            self.generic_visit(node)
            return node

    DocStripper().visit(tree)


def write_output(
    src_root: Path,
    out_root: Path,
    files: list[Path],
    trees: dict[Path, ast.Module],
    rename: dict[str, str],
    mod_rename: dict[tuple[str, ...], tuple[str, ...]],
) -> None:
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    for f in files:
        parts = module_path_from(src_root, f)
        rel = f.relative_to(src_root)
        is_init = rel.name == "__init__.py"
        if rel == Path("main.py"):
            out_path = out_root / "main.py"
        elif is_init:
            # Package __init__.py: keep name, but use renamed package dir.
            new_parts = mod_rename.get(parts, parts)
            out_path = out_root.joinpath(*new_parts, "__init__.py")
        else:
            new_parts = mod_rename.get(parts, parts)
            if not new_parts:
                out_path = out_root / f"{rename.get(rel.stem, rel.stem)}.py"
            else:
                *dirs, last = new_parts
                out_path = out_root.joinpath(*dirs, f"{last}.py")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tree = trees[f]
        src = ast.unparse(tree)
        out_path.write_text(src + "\n")


def sanity_checks(src_root: Path, files: list[Path]) -> None:
    for f in files:
        text = f.read_text()
        if re.search(r"\bgetattr\s*\(", text):
            print(
                f"warning: {f.relative_to(src_root)} uses getattr — verify "
                "attribute names aren't obfuscated away",
                file=sys.stderr,
            )
        if re.search(r"\bsetattr\s*\(", text):
            print(
                f"warning: {f.relative_to(src_root)} uses setattr — "
                "obfuscation may break it",
                file=sys.stderr,
            )
        if re.search(r"\b__import__\s*\(", text):
            print(
                f"warning: {f.relative_to(src_root)} uses __import__",
                file=sys.stderr,
            )


def main() -> None:
    ap = argparse.ArgumentParser(description="AST-rename obfuscate a bot.")
    ap.add_argument("bot")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    src_root = Path(args.bot).resolve()
    if not src_root.is_dir():
        cand = Path("bots") / args.bot
        if cand.is_dir():
            src_root = cand.resolve()
    if not (src_root / "main.py").is_file():
        print(f"error: {src_root}/main.py not found", file=sys.stderr)
        sys.exit(1)

    out_root = (
        Path(args.out).resolve()
        if args.out
        else src_root.with_name(src_root.name + "-obf")
    )

    files = collect_py_files(src_root)
    sanity_checks(src_root, files)
    local_modules = collect_local_modules(src_root, files)
    trees = parse_all(files)

    names = collect_names(trees, local_modules)
    stdlib_attrs = frozenset(collect_stdlib_attrs(trees, local_modules))
    kwarg_names: set[str] = set()
    for t in trees.values():
        for node in ast.walk(t):
            if isinstance(node, ast.keyword) and node.arg is not None:
                kwarg_names.add(node.arg)
    rename, mod_rename = build_rename_map(
        names, local_modules, stdlib_attrs | frozenset(kwarg_names)
    )

    rewriter = Rewriter(rename, local_modules)
    for f in files:
        strip_docstrings(trees[f])
        strip_annotations(trees[f])
        strip_type_imports(trees[f])
        trees[f] = rewriter.visit(trees[f])  # type: ignore[assignment]
        ast.fix_missing_locations(trees[f])

    write_output(src_root, out_root, files, trees, rename, mod_rename)
    print(out_root)


if __name__ == "__main__":
    main()
