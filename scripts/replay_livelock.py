import sys

from scripts.replay import load_replay


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "replay.replay26"
    team = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    r = load_replay(path)

    entity_team: dict[int, int] = {}
    positions: dict[int, list[tuple[int, str]]] = {}

    for i, turn in enumerate(r.turns):
        for u in turn.updates:
            for fd, val in u.ListFields():
                if fd.name == "place_entity":
                    entity_team[val.entity.id] = val.entity.team
            if u.HasField("bot_output") and entity_team.get(u.bot_output.id) == team:
                bo = u.bot_output
                move = ""
                for line in bo.stdout.split("\n"):
                    line = line.strip()
                    if any(
                        x in line
                        for x in [
                            "MoveOnly",
                            "ActionOnly",
                            "MoveAction",
                            "ActionMove",
                            "Wait",
                        ]
                    ):
                        move = line
                        break
                if bo.id not in positions:
                    positions[bo.id] = []
                positions[bo.id].append((i + 1, move))

    found = False
    for eid, entries in sorted(positions.items()):
        for period in [2, 3, 4]:
            for j in range(len(entries) - period * 3):
                seq = [e[1] for e in entries[j : j + period * 3]]
                chunks = [
                    tuple(seq[k : k + period]) for k in range(0, period * 3, period)
                ]
                if (
                    chunks[0] == chunks[1] == chunks[2]
                    and len(set(chunks[0])) > 1
                ):
                    t_start = entries[j][0]
                    t_end = entries[j + period * 3 - 1][0]
                    print(f"LIVELOCK id={eid} t={t_start}-{t_end} period={period}")
                    for k in range(period * 2):
                        t = entries[j + k][0]
                        for u in r.turns[t - 1].updates:
                            if (
                                u.HasField("bot_output")
                                and u.bot_output.id == eid
                            ):
                                task_lines = [
                                    line.strip()
                                    for line in u.bot_output.stdout.split("\n")
                                    if "    " in line
                                    or ("task=" in line and "OK" in line)
                                ]
                                tl = task_lines[0] if task_lines else "?"
                                print(
                                    f"  t={t}: {tl} | {entries[j + k][1][:60]}"
                                )
                    print()
                    found = True
                    break
            else:
                continue
            break

    # Deadlock: all builders returning Wait for multiple consecutive turns
    all_ids = sorted(positions.keys())
    if len(all_ids) > 1:
        max_turns = len(r.turns)
        for t in range(max_turns - 5):
            all_wait = True
            for eid in all_ids:
                es = [e for e in positions[eid] if e[0] == t + 1]
                if not es or "Wait" not in es[0][1]:
                    all_wait = False
                    break
            if all_wait:
                streak = 1
                for t2 in range(t + 1, min(t + 20, max_turns)):
                    still_wait = True
                    for eid in all_ids:
                        es = [e for e in positions[eid] if e[0] == t2 + 1]
                        if not es or "Wait" not in es[0][1]:
                            still_wait = False
                            break
                    if still_wait:
                        streak += 1
                    else:
                        break
                if streak >= 4:
                    print(
                        f"DEADLOCK t={t+1}-{t+streak} all {len(all_ids)} builders waiting"
                    )
                    found = True
                    break

    if not found:
        print("No livelock or deadlock detected.")


if __name__ == "__main__":
    main()
