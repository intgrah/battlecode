"""Run all analysis scripts on a replay and produce a comprehensive report."""

import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    "replay_economy.py",
    "replay_builders.py",
    "replay_flow.py",
    "replay_spatial.py",
    "replay_oscillation.py",
    "replay_markers.py",
    "replay_infrastructure.py",
    "replay_ore_timeline.py",
    "replay_network.py",
    "replay_throughput.py",
    "replay_health.py",
    "replay_combat.py",
    "replay_vulnerability.py",
]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: replay_full.py <replay_path> [--brief]")
        sys.exit(1)

    replay = sys.argv[1]
    brief = "--brief" in sys.argv
    scripts_dir = Path(__file__).resolve().parent

    print(f"{'=' * 60}")
    print(f"FULL REPLAY ANALYSIS: {replay}")
    print(f"{'=' * 60}")

    for script in SCRIPTS:
        script_path = scripts_dir / script
        if not script_path.exists():
            continue

        print(f"\n{'─' * 60}")
        print(f"  {script}")
        print(f"{'─' * 60}")

        try:
            result = subprocess.run(
                [sys.executable, str(script_path), replay],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            output = result.stdout.strip()
            if brief:
                lines = output.split("\n")
                for line in lines[:20]:
                    print(line)
                if len(lines) > 20:
                    print(f"  ... ({len(lines) - 20} more lines)")
            else:
                print(output)
            if result.stderr.strip():
                err_lines = result.stderr.strip().split("\n")
                if "Traceback" in result.stderr:
                    print(f"  [ERROR] {err_lines[-1]}")
        except subprocess.TimeoutExpired:
            print("  [TIMEOUT]")
        except (subprocess.SubprocessError, OSError) as e:
            print(f"  [ERROR] {e}")

    print(f"\n{'=' * 60}")
    print("ANALYSIS COMPLETE")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
