"""Smoke check that one request is drawn with the matching graph CSV."""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visualizations import requests_map


def test_requests_map():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        run = root / "outputs" / "requests" / "sample"
        graph = root / "outputs" / "graphs" / "test"
        run.mkdir(parents=True)
        graph.mkdir(parents=True)
        (run / "requests.json").write_text(json.dumps({"requests": {
            "4": {"origin": [49.5, 6.0], "destination": [49.51, 6.01]}}}))
        (run / "parameters.txt").write_text('task = "DARP"\nmap = "test"\nbusline = null\n')
        (graph / "drive_nodes.csv").write_text(
            "osmid,x,y,geometry\n1,6.0,49.5,\n2,6.01,49.51,\n")
        (graph / "drive_edges.csv").write_text(
            'u,v,key,length,geometry\n1,2,0,100,"LINESTRING (6.0 49.5, 6.01 49.51)"\n')
        (graph / "pois.json").write_text(json.dumps({"features": [
            {"lat": 49.505, "lon": 6.005}]}))
        (graph / "depot.json").write_text(json.dumps({
            "drive_point": [49.5, 6.0], "original_point": [49.5, 6.0],
            "snap_distance_m": 0}))
        (graph / "service_area.geojson").write_text(json.dumps({
            "geometry": {"type": "Polygon", "coordinates": [[
                [6.0, 49.5], [6.01, 49.5], [6.01, 49.51], [6.0, 49.5]]]}}))
        old_root = requests_map.ROOT
        try:
            requests_map.ROOT = root
            output = requests_map.draw_requests_map("test", "sample", root / "map.png")
            assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

            busline_dir = root / "data" / "buslines" / "550"
            busline_dir.mkdir(parents=True)
            (busline_dir / "businfo.json").write_text(json.dumps({
                "stops": [{"stop_id": "a", "stop_lon": 6.0, "stop_lat": 49.5},
                          {"stop_id": "b", "stop_lon": 6.01, "stop_lat": 49.51}],
                "patterns": [{"stop_ids": ["a", "b"]}]}))
            (run / "parameters.txt").write_text('task = "SFBS"\nmap = "test"\nbusline = "550"\n')
            (graph / "depot.json").write_text(json.dumps({
                "drive_point": [49.5, 6.0], "original_point": [49.53, 5.98],
                "snap_distance_m": 4000}))
            with patch.object(requests_map.plt, "close") as close:
                output = requests_map.draw_requests_map("test", "sample", root / "sfbs.png")
            figure = close.call_args.args[0]
            routes = [item for item in figure.axes[0].collections
                      if item.get_label() == "Bus 550 (stops linked)"]
            assert len(routes) == 1
            assert routes[0].get_segments()[0].tolist() == [[6.0, 49.5], [6.01, 49.51]]
            assert [item.get_text() for item in figure.axes[0].get_legend().texts].count("Depot") == 1
            requests_map.plt.close(figure)
        finally:
            requests_map.ROOT = old_root
        assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    test_requests_map()
