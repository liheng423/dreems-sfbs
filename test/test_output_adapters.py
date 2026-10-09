"""Check independent busline/graph selection and numbered request outputs."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.output_adapters import (GRAPH_FILES, REQUEST_FILES,
                                 available_buslines, available_graphs, busline_dir,
                                 busline_path, create_request_dir, graph_dir, graph_path,
                                 request_path, write_json)


def test_output_layout():
    """A 605 busline may use the 550 graph without reusing an output directory."""
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        buslines_dir = data_dir / "buslines"
        graphs_dir = data_dir / "graphs"
        requests_dir = data_dir / "requests"
        requests_dir.mkdir()
        route_dir = busline_dir("605", buslines_dir)
        for name in ("businfo", "stops"):
            path = busline_path(name, route_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        area_dir = graph_dir("550", graphs_dir)
        for name in GRAPH_FILES:
            path = graph_path(name, area_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(name)
        assert available_buslines(buslines_dir) == ["605"]
        assert available_graphs(graphs_dir) == ["550"]
        assert area_dir.parent == graphs_dir

        first = create_request_dir("605", "550", requests_dir)
        second = create_request_dir("605", "550", requests_dir)
        assert (first.name, second.name) == ("605_550_0001", "605_550_0002")
        for number, instance_dir in enumerate((first, second), 1):
            for name in REQUEST_FILES:
                write_json(request_path(name, instance_dir), {"run": number})
            assert {path.name for path in instance_dir.iterdir()} == set(REQUEST_FILES.values())
        assert request_path("pool", first).read_text() != request_path("pool", second).read_text()


if __name__ == "__main__":
    test_output_layout()
