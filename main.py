"""Run the service-area selector or synthetic-demand generator."""

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
COMMANDS = {
    "select-area": ROOT / "src/crawler/service_area/define_service_area.py",
    "generate-demand": ROOT / "src/reqreate/generate.py",
}


def main():
    """Dispatch a project command with the current Python environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()
    subprocess.run([sys.executable, str(COMMANDS[args.command])], check=True)


if __name__ == "__main__":
    main()
