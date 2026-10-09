# Busline energy reference and configuration

Source: Sammy Jablonski, Benedikt Tepe, Yuqing Zhao, and Andreas Jossen, “Analysis and Characterization of the Energy Consumption in an Electric Bus Fleet,” NEIS 2023, pp. 255–261. Local copy: [paper](../../.ref/papers/Analysis_and_Characterization_of_the_Energy_Consumption_in_an_Electric_Bus_Fleet.pdf). The values below are from **Table 1, printed p. 256**, unless another page or section is named. `energy.toml` transcribes the Table 1 values; `energy.py` uses them to estimate energy for each consecutive stop pair on the selected route.

## What the paper measured

| Item | Reported value or condition | Source and use |
| --- | --- | --- |
| Fleet | 101 Hamburg buses: 85 Evobus and 16 Solaris; 86 non-articulated (NA, 12 m) and 15 articulated (AR, 18 m) | Table 1 caption, p. 256. This is **not** an identified fleet for the selected route. |
| Heating | 82 NA and 15 AR buses use hybrid heating (HHS); 4 NA buses use electric-only heating (EHS) | Section 2, p. 256. Evobus fossil-heating threshold: 8 °C; Solaris: 5 °C. |
| Empty mass | NA: 13.8–14.6 t; AR: 20.3–20.7 t | Section 2, p. 256. A range, not a per-model mass or a calibrated energy coefficient. |
| Data and trip filter | Mileage, state of charge, and ambient temperature sampled every 10 s. 40,279 accepted trips, each >2 and <24 h with 20–300 km mileage change | Section 2, pp. 256–257. Trip energy was derived from state-of-energy and mileage changes. |
| Reference temperature | 20–22 °C gives minimum median consumption | Table 1, p. 256. `reference_20_22_c` selects this measured case. |
| Other temperature cases | Table 1 gives relative changes at 0, 9, and 30 °C against the 20–22 °C median | `at_0_c`, `at_9_c`, `at_30_c` select these exact cases. No interpolation is applied. |
| Fleet-level context | About 0.92 kWh/km for NA and 1.27 kWh/km for AR at 20–22 °C | Abstract, p. 255. Approximate fleet summaries; the helper uses the more specific Table 1 profiles. |

## Table 1 profiles

`Δ` is the reported increase relative to the profile's 20–22 °C median. A dash means Table 1 has no value. NMC = lithium nickel manganese cobalt; LMP = lithium metal polymer.

| TOML profile | Manufacturer / type / heating | Battery | Seats or passenger capacity | Buses | 20–22 °C kWh/km | Δ 0 °C | Δ 9 °C | Δ 30 °C |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `evobus_243_nmc_na_hybrid` | Evobus eCitaro / NA / hybrid | 243 kWh NMC | 88 | 20 | 0.90 | 12% | 26% | 24% |
| `evobus_396_nmc_na_hybrid` | Evobus eCitaro / NA / hybrid | 396 kWh NMC | 88 | 11 | 0.87 | 29% | 29% | 19% |
| `evobus_396_nmc_na_electric` | Evobus eCitaro / NA / electric | 396 kWh NMC | 88 | 1 | 0.84 | 94% | 33% | — |
| `evobus_396_nmc_ar_hybrid` | Evobus eCitaro / AR / hybrid | 396 kWh NMC | 146 | 10 | 1.23 | 21% | 27% | 36% |
| `evobus_441_lmp_na_hybrid` | Evobus eCitaro / NA / hybrid | 441 kWh LMP | 88 | 36 | 0.98 | 24% | 29% | 16% |
| `evobus_441_lmp_na_electric` | Evobus eCitaro / NA / electric | 441 kWh LMP | 88 | 2 | 1.02 | 70% | 33% | — |
| `evobus_441_lmp_ar_hybrid` | Evobus eCitaro / AR / hybrid | 441 kWh LMP | 146 | 5 | 1.35 | 27% | 27% | 33% |
| `solaris_300_nmc_na_hybrid` | Solaris Urbino / NA / hybrid | 300 kWh NMC | 85 | 10 | 0.94 | 6% | 49% | 25% |
| `solaris_396_nmc_na_hybrid` | Solaris Urbino / NA / hybrid | 396 kWh NMC | 85 | 5 | 0.82 | 14% | 64% | 21% |
| `solaris_396_nmc_na_electric` | Solaris Urbino / NA / electric | 396 kWh NMC | 85 | 1 | 0.91 | 71% | 43% | — |

Table 1 calls the capacity column “Passenger Capacity”; it does not distinguish seated from standing places. Electric-only groups have only 1–2 buses and no reported 30 °C increase.

## Conditions that are not model coefficients

| Finding | Conditions and limits | Treatment |
| --- | --- | --- |
| Heating and cooling | Below 20 °C and above the fossil-heating threshold, consumption increases roughly linearly. The conclusion reports 2.5–3.5%/K for Evobus below 20 °C, 1.5–2.5%/K for NA above 22 °C, and 3.5%/K for AR above 22 °C (p. 260). Below the HHS threshold the response depends on the manufacturer and heating strategy. | These are ranges, so the helper uses Table 1's exact temperature cases instead of choosing a slope. |
| Rain | Figure 3 and Section 5.1, pp. 259–260: at 9–10 °C, selected models showed 6–13% higher median consumption in rain; weather data are sparse and rain effects usually remain under about 10%. | No universal rain multiplier is entered in TOML. |
| Snow | Section 5.2, p. 260: effect was inconclusive, typically <5%. | No snow multiplier is entered. |
| Road speed or type | The paper discusses these as possible influences but provides no speed-to-energy or road-class coefficient for the fleet. | GraphML road lengths determine segment distance. Speed and road class do **not** change kWh/km. |
| Mechanical parameters | No per-model rolling resistance, drag area, drivetrain efficiency, regeneration efficiency, or auxiliary power is reported. | The previous unreferenced mechanical constants were removed. |

## Route calculation

The explicit scenario in [energy.toml](energy.toml) selects `evobus_396_nmc_na_hybrid` at `reference_20_22_c`. This is an **illustrative profile**, not a claim that the selected route uses that bus or that its ambient temperature was 20–22 °C. Change both keys to match a known vehicle and measured condition before treating the result as a route estimate. The selected profile's `reference_kwh_per_km` is multiplied by `1 + relative_increase_pct / 100` for the selected temperature case; each segment's energy is then `road_distance_m / 1000 × selected_kwh_per_km`.

The distance is a directed shortest path by GraphML edge length between the nearest road nodes, not a recorded bus path. If two stops snap to the same simplified node, the helper marks and uses their straight-line separation as a lower bound. Table 1 rates came from 20–300 km trips, so allocating one trip-average rate to every short segment is an approximation; the paper does not resolve stop-by-stop acceleration or route-specific passenger loads.

After changing `energy.toml`, regenerate `data/buslines/<route>/energy.json` from the repository root with `python3 src/busline/energy.py --route <route>`. The command reads that route's `businfo.json` and `data/graphs/<route>/drive.graphml`; both files must already exist. Segment stop IDs are the GTFS stop IDs from `businfo.json`.

```python
import json
import tomllib
import osmnx as ox

from energy import estimate_busline_energy

with open("src/busline/energy.toml", "rb") as file:
    config = tomllib.load(file)
with open("data/buslines/550/businfo.json") as file:
    businfo = json.load(file)
graph = ox.load_graphml("data/graphs/550/drive.graphml")
segments = estimate_busline_energy(graph, businfo, config)
```
