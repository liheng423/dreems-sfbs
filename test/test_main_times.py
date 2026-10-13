"""Check repeated demand generation at the public command boundary."""

import sys
import tomllib
from unittest.mock import call, patch

import main


def test_generate_demand_times():
    argv = ["main.py", "generate-demand", "SFBS", "--map", "550",
            "--busline", "605", "--times", "3", "--debug"]
    with patch.object(sys, "argv", argv), patch.object(main.subprocess, "run") as run:
        main.main()
    command = [sys.executable, str(main.COMMANDS["generate-demand"]),
               "SFBS", "--map", "550", "--busline", "605", "--debug"]
    seed = tomllib.loads((main.ROOT / "src/reqreate/request_gen.toml").read_text())["seed"]
    assert run.call_args_list == [
        call([*command, "--seed", str(seed + offset)], check=True)
        for offset in range(3)
    ]


def test_recrawl_pois_command():
    with patch.object(sys, "argv", ["main.py", "recrawl-pois", "Esch"]), patch.object(
        main.subprocess, "run"
    ) as run:
        main.main()
    run.assert_called_once_with(
        [sys.executable, str(main.COMMANDS["recrawl-pois"]), "--map", "Esch", "--recrawl-pois"],
        check=True,
    )
