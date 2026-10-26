"""Run with: python -m unittest test.test_crawl_gtfs_generic"""

import datetime as dt
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.crawler.busline.crawl_gtfs import crawl


ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\nA,Test Transit,https://example.org,Europe/Brussels\n",
    "feed_info.txt": "feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,feed_end_date\nTest Publisher,https://example.org,en,20261001,20261031\n",
    "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type\nR1,A,12,Test route,3\n",
    "calendar_dates.txt": "service_id,date,exception_type\nS,20261019,1\n",
    "trips.txt": "route_id,service_id,trip_id,direction_id\nR1,S,T1,0\n",
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence,shape_dist_traveled\n"
        "T1,06:00:00,06:00:00,S1,1,0\n"
        "T1,,,S2,2,2\n"
        "T1,06:20:00,06:20:00,S3,3,10\n"
    ),
    "stops.txt": (
        "stop_id,stop_name,stop_lat,stop_lon\n"
        "S1,First,50.1,4.1\nS2,Middle,50.2,4.2\nS3,Last,50.3,4.3\n"
    ),
}


def make_zip(tables=TABLES):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in tables.items():
            archive.writestr(name, content)
    return output.getvalue()


class GenericGTFS(unittest.TestCase):
    def test_calendar_dates_only_and_untimed_stop(self):
        result = crawl(make_zip(), "feed.zip", "", None, dt.date(2026, 10, 19), "R1")
        self.assertEqual(result["source"]["producer"], "Test Publisher")
        self.assertEqual(result["source"]["agency_timezone"], "Europe/Brussels")
        self.assertEqual(result["source"]["license"], "")
        self.assertEqual(result["source"]["feed_service_range"], ["20261001", "20261031"])
        times = result["patterns"][0]["trips"][0]["stop_times"]
        self.assertEqual(times[1]["arrival_time"], "06:04:00")
        self.assertEqual(times[1]["departure_seconds"], 21840)

    def test_cli_uses_operator_folder_and_local_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "feed.zip"
            archive.write_bytes(make_zip())
            output = root / "tec-12" / "buslines.json"
            command = [
                sys.executable, str(ROOT / "crawl_busline.py"),
                "--gtfs-zip", str(archive), "--route-id", "R1",
                "--service-date", "2026-10-19", "--output", str(output),
                "--source-url", "https://example.org/feed.zip", "--license", "Example license",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True, cwd=ROOT)
            result = json.loads(output.read_text())
            self.assertEqual(result["source"]["source_url"], "https://example.org/feed.zip")
            self.assertEqual(result["source"]["license"], "Example license")
            self.assertTrue(output.with_name("stops.json").is_file())
            stops_path = output.with_name("stops.json")
            stops = json.loads(stops_path.read_text())
            stops[0]["class"] = "optional"
            stops.append({"name": "Stop_OSM_42", "type": "location", "class": "mandatory",
                          "lon": 4.4, "lat": 50.4})
            stops_path.write_text(json.dumps(stops))
            subprocess.run(command, check=True, capture_output=True, text=True, cwd=ROOT)
            preserved = json.loads(stops_path.read_text())
            self.assertEqual(preserved[0]["class"], "optional")
            self.assertEqual(preserved[-1]["name"], "Stop_OSM_42")

    def test_frequency_trips_fail_explicitly(self):
        tables = dict(TABLES, **{
            "frequencies.txt": "trip_id,start_time,end_time,headway_secs\nT1,06:00:00,07:00:00,600\n"
        })
        with self.assertRaisesRegex(ValueError, "frequency-based service"):
            crawl(make_zip(tables), "feed.zip", "", "12", dt.date(2026, 10, 19))

    def test_exact_frequency_trips_expand(self):
        tables = dict(TABLES, **{
            "frequencies.txt": (
                "trip_id,start_time,end_time,headway_secs,exact_times\n"
                "T1,07:00:00,07:21:00,600,1\n"
            )
        })
        result = crawl(make_zip(tables), "feed.zip", "", "12", dt.date(2026, 10, 19))
        trips = result["patterns"][0]["trips"]
        self.assertEqual([trip["stop_times"][0]["departure_time"] for trip in trips],
                         ["07:00:00", "07:10:00", "07:20:00"])
        self.assertEqual(trips[1]["stop_times"][1]["arrival_time"], "07:14:00")

    def test_calendar_without_exceptions(self):
        tables = dict(TABLES)
        del tables["calendar_dates.txt"]
        tables["calendar.txt"] = (
            "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            "S,1,0,0,0,0,0,0,20261001,20261031\n"
        )
        result = crawl(make_zip(tables), "feed.zip", "", "12", dt.date(2026, 10, 19))
        self.assertEqual(result["active_service_ids"], ["S"])


if __name__ == "__main__":
    unittest.main()
