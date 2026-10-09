"""Select a route's graph area, generate demand, or explore the results."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import webbrowser


ROOT = Path(__file__).resolve().parent
COMMANDS = {
    "select-area": ROOT / "src/crawler/service_area/define_service_area.py",
    "generate-demand": ROOT / "src/reqreate/generate.py",
}


def serve_visualizer():
    """Serve repository data and open the interactive visualizer."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        url = f"http://127.0.0.1:{server.server_port}/interactive_visualizer/"
        print(f"Opening {url}", flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped visualizer.")


def main():
    """Dispatch a project command with the current Python environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    area = commands.add_parser("select-area")
    area.add_argument("map")
    area.add_argument("--busline")
    demand = commands.add_parser("generate-demand")
    demand.add_argument("--map", required=True)
    demand.add_argument("--busline")
    demand.add_argument("--requests", type=int)
    commands.add_parser("visualize")
    args = parser.parse_args()
    if args.command == "visualize":
        serve_visualizer()
        return
    if args.command == "select-area":
        step_args = ["--map", args.map]
        if args.busline:
            step_args.extend(["--busline", args.busline])
    else:
        step_args = ["--map", args.map]
        if args.busline:
            step_args.extend(["--busline", args.busline])
        if args.requests is not None:
            step_args.extend(["--requests", str(args.requests)])
    subprocess.run([sys.executable, str(COMMANDS[args.command]), *step_args], check=True)


if __name__ == "__main__":
    main()
