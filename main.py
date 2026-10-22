"""Select map areas or graph locations, generate demand, or explore results."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tomllib
import webbrowser


ROOT = Path(__file__).resolve().parent
COMMANDS = {
    "select-area": ROOT / "src/crawler/service_area/define_service_area.py",
    "select-locations": ROOT / "src/locations/select_locations.py",
    "recrawl-pois": ROOT / "src/crawler/service_area/define_service_area.py",
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


def generate_demand(args):
    """Run demand generation once per requested instance."""
    step_args = [args.task, "--map", args.map]
    if args.busline:
        step_args.extend(["--busline", args.busline])
    if args.debug:
        step_args.append("--debug")
    seed = (tomllib.loads((ROOT / "src/reqreate/request_gen.toml").read_text())["seed"]
            if args.times > 1 else None)
    for offset in range(args.times):
        run_args = [*step_args, "--seed", str(seed + offset)] if seed is not None else step_args
        subprocess.run([sys.executable, str(COMMANDS["generate-demand"]), *run_args], check=True)


def main():
    """Dispatch a project command with the current Python environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    area = commands.add_parser("select-area")
    area.add_argument("map")
    area.add_argument("--busline")
    locations = commands.add_parser("select-locations", help="Choose locations on an existing driving graph")
    locations.add_argument("map")
    recrawl = commands.add_parser("recrawl-pois", help="Update POIs for a saved graph area")
    recrawl.add_argument("map")
    demand = commands.add_parser("generate-demand")
    demand.add_argument("task", choices=("DARP", "SFBS"))
    demand.add_argument("--map", required=True)
    demand.add_argument("--busline")
    demand.add_argument("--debug", action="store_true")
    demand.add_argument("--times", type=int, default=1, help="Number of instances to generate (default: 1)")
    commands.add_parser("visualize")
    args = parser.parse_args()
    if args.command == "generate-demand":
        if args.task == "SFBS" and not args.busline:
            demand.error("SFBS requires --busline")
        if args.task == "DARP" and args.busline:
            demand.error("DARP does not use --busline")
        if args.times < 1:
            demand.error("--times must be at least 1")
        generate_demand(args)
        return
    if args.command == "visualize":
        serve_visualizer()
        return
    step_args = ["--map", args.map]
    if args.command == "recrawl-pois":
        step_args.append("--recrawl-pois")
    elif args.command == "select-area" and args.busline:
        step_args.extend(["--busline", args.busline])
    subprocess.run([sys.executable, str(COMMANDS[args.command]), *step_args], check=True)


if __name__ == "__main__":
    main()
