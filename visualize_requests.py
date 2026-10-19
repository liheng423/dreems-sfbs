"""Create a PNG with saved requests and their road network."""

import argparse

from visualizations.requests_map import draw_requests_map


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", required=True, help="Folder name under outputs/graphs")
    parser.add_argument("--instance", required=True, help="Folder name under outputs/requests")
    parser.add_argument("--output", help="PNG output path")
    args = parser.parse_args()
    print(draw_requests_map(args.map, args.instance, args.output))
