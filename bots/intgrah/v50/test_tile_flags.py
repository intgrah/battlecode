from constants import COST_EMPTY, COST_IMPASSABLE, COST_ROAD, COST_UNSEEN
from tile_flags import (
    B_ARMOURED_CONVEYOR,
    B_BARRIER,
    B_BREACH,
    B_BRIDGE,
    B_CONVEYOR,
    B_CORE,
    B_FOUNDRY,
    B_GUNNER,
    B_HARVESTER_AX,
    B_HARVESTER_TI,
    B_LAUNCHER,
    B_MARKER,
    B_ROAD,
    B_SENTINEL,
    B_SPLITTER,
    EMPTY,
    ORE_AX,
    ORE_TI,
    UNSEEN,
    WALK_COST,
    WALL,
    building_type,
    has_building,
    is_enemy,
    is_friendly,
    is_harvester,
    is_passable,
    is_transport,
    is_turret,
    is_unseen,
    is_walkable_building,
    is_wall_or_ore,
    make_building,
)


def test_env_states() -> None:
    assert UNSEEN == 0
    assert is_unseen(UNSEEN)
    assert WALK_COST[UNSEEN] == COST_UNSEEN

    assert is_wall_or_ore(WALL)
    assert not is_passable(WALL)
    assert WALK_COST[WALL] == COST_IMPASSABLE

    assert is_wall_or_ore(ORE_TI)
    assert is_wall_or_ore(ORE_AX)
    assert WALK_COST[ORE_TI] == COST_IMPASSABLE
    assert WALK_COST[ORE_AX] == COST_IMPASSABLE

    assert is_passable(EMPTY)
    assert not has_building(EMPTY)
    assert WALK_COST[EMPTY] == COST_EMPTY


def test_friendly_transport() -> None:
    for btype in (B_ROAD, B_CONVEYOR, B_ARMOURED_CONVEYOR, B_SPLITTER, B_BRIDGE):
        f = make_building(btype, enemy=False)
        assert is_passable(f)
        assert has_building(f)
        assert not is_enemy(f)
        assert is_friendly(f)
        assert building_type(f) == btype
        assert WALK_COST[f] == COST_ROAD, f"btype={btype}"


def test_transport_vs_road() -> None:
    assert not is_transport(make_building(B_ROAD))
    for btype in (B_CONVEYOR, B_ARMOURED_CONVEYOR, B_SPLITTER, B_BRIDGE):
        assert is_transport(make_building(btype))
        assert is_transport(make_building(btype, enemy=True))


def test_enemy_transport() -> None:
    for btype in (B_ROAD, B_CONVEYOR, B_ARMOURED_CONVEYOR, B_SPLITTER, B_BRIDGE):
        f = make_building(btype, enemy=True)
        assert has_building(f)
        assert is_enemy(f)
        assert not is_friendly(f)
        assert WALK_COST[f] == COST_IMPASSABLE


def test_friendly_core() -> None:
    f = make_building(B_CORE, enemy=False)
    assert WALK_COST[f] == COST_ROAD
    assert is_walkable_building(f)
    assert not is_transport(f)
    assert not is_turret(f)


def test_enemy_core() -> None:
    f = make_building(B_CORE, enemy=True)
    assert WALK_COST[f] == COST_IMPASSABLE
    assert not is_walkable_building(f)


def test_markers() -> None:
    f = make_building(B_MARKER, enemy=False)
    assert WALK_COST[f] == COST_EMPTY
    assert has_building(f)
    f = make_building(B_MARKER, enemy=True)
    assert WALK_COST[f] == COST_EMPTY


def test_impassable_buildings() -> None:
    for btype in (B_BARRIER, B_HARVESTER_TI, B_HARVESTER_AX, B_FOUNDRY):
        for enemy in (False, True):
            f = make_building(btype, enemy=enemy)
            assert WALK_COST[f] == COST_IMPASSABLE, f"btype={btype} enemy={enemy}"
            assert not is_walkable_building(f)


def test_turrets() -> None:
    for btype in (B_GUNNER, B_SENTINEL, B_BREACH, B_LAUNCHER):
        for enemy in (False, True):
            f = make_building(btype, enemy=enemy)
            assert is_turret(f), f"btype={btype}"
            assert not is_transport(f)
            assert WALK_COST[f] == COST_IMPASSABLE


def test_harvesters() -> None:
    f_ti = make_building(B_HARVESTER_TI, enemy=False)
    f_ax = make_building(B_HARVESTER_AX, enemy=False)
    assert is_harvester(f_ti)
    assert is_harvester(f_ax)
    assert not is_harvester(EMPTY)
    assert not is_harvester(make_building(B_CONVEYOR))
    assert building_type(f_ti) == B_HARVESTER_TI
    assert building_type(f_ax) == B_HARVESTER_AX


def test_transport_mask() -> None:
    transport_types = (B_CONVEYOR, B_ARMOURED_CONVEYOR, B_SPLITTER, B_BRIDGE)
    non_transport = (
        B_ROAD,
        B_MARKER,
        B_BARRIER,
        B_HARVESTER_TI,
        B_FOUNDRY,
        B_GUNNER,
        B_SENTINEL,
        B_BREACH,
        B_LAUNCHER,
        B_CORE,
        B_HARVESTER_AX,
    )
    for btype in transport_types:
        assert is_transport(make_building(btype))
        assert is_transport(make_building(btype, enemy=True))
    for btype in non_transport:
        assert not is_transport(make_building(btype)), f"btype={btype}"


def test_turret_mask() -> None:
    turret_types = (B_GUNNER, B_SENTINEL, B_BREACH, B_LAUNCHER)
    non_turret = (
        B_ROAD,
        B_CONVEYOR,
        B_ARMOURED_CONVEYOR,
        B_SPLITTER,
        B_BRIDGE,
        B_MARKER,
        B_BARRIER,
        B_HARVESTER_TI,
        B_HARVESTER_AX,
        B_FOUNDRY,
        B_CORE,
    )
    for btype in turret_types:
        assert is_turret(make_building(btype))
    for btype in non_turret:
        assert not is_turret(make_building(btype)), f"btype={btype}"


def test_walkable_building_mask() -> None:
    walkable = (B_ROAD, B_CONVEYOR, B_ARMOURED_CONVEYOR, B_SPLITTER, B_BRIDGE, B_CORE)
    for btype in walkable:
        assert is_walkable_building(make_building(btype, enemy=False))
        assert not is_walkable_building(make_building(btype, enemy=True))


def test_walk_cost_completeness() -> None:
    for b in range(256):
        c = WALK_COST[b]
        assert c in (COST_UNSEEN, COST_IMPASSABLE, COST_EMPTY, COST_ROAD), (
            f"byte=0b{b:08b} cost={c}"
        )


def main() -> None:
    test_env_states()
    test_friendly_transport()
    test_transport_vs_road()
    test_enemy_transport()
    test_friendly_core()
    test_enemy_core()
    test_markers()
    test_impassable_buildings()
    test_turrets()
    test_harvesters()
    test_transport_mask()
    test_turret_mask()
    test_walkable_building_mask()
    test_walk_cost_completeness()
    print("All tests passed.")


if __name__ == "__main__":
    main()
