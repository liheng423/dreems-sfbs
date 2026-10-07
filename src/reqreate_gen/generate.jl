#!/usr/bin/env julia

#=
Build a directed-route network, scheduled-time matrix, and demand scenarios.

The command consumes normalized GTFS JSON from the Python crawler. It writes
the corridor, full trip timetable, candidate pool, and low/base/high JSON
instances. Passenger requests are synthetic scenario assumptions, not
observed ridership. Scenario trip energy uses the distance matrix beside the
GTFS input, named `distance_matrix_<line or network>.json`.

# Arguments

- `in_path`: normalized crawler JSON input (defaults to `data/crawled_550.json`).
- `out_dir`: directory for generated files (defaults to `data/`).
- `class_path`: source-stop classification JSON (defaults to Route 550 classes).
- `--fleet-type`: electric (default) or conventional bus profile.
- `--energy-rate-kwh-per-km`: optional replacement for the selected profile rate.
=#
using JSON3

include("types.jl")
include("demand_config.jl")
include("fleet_config.jl")
include("fleet.jl")

const SCRIPT_DIR = @__DIR__
const PROJECT_ROOT = dirname(dirname(SCRIPT_DIR))
const DATA_DIR = joinpath(PROJECT_ROOT, "data")
const CRAWLED_PATH = joinpath(DATA_DIR, "crawled_550.json")
const CLASS_PATH = joinpath(SCRIPT_DIR, "stop_classes_550.json")

include(joinpath(@__DIR__, "..", "utilities", "utilities.jl"))

include("routes.jl")
include(joinpath("input_adapters", "network.jl"))
include(joinpath("demand_generators", "eligibility.jl"))
include(joinpath("demand_generators", "allocations.jl"))
include(joinpath("demand_generators", "demand.jl"))
include(joinpath("output_adapters", "output.jl"))

"""
Read GTFS and its road-distance matrix, then write the shared data and selected fleet scenarios.
"""
function main(in_path::String=CRAWLED_PATH, out_dir::String=DATA_DIR, class_path::String=CLASS_PATH;
              fleet_type::String="electric", energy_rate_kwh_per_km::Union{Nothing, Float64}=nothing)
    in_path = abspath(in_path)
    out_dir = abspath(out_dir)
    crawl = JSON3.read(read(in_path, String))
    class_cfg = JSON3.read(read(class_path, String))
    net, timetable_patterns, hrs = build_net(crawl, class_cfg)
    net_out = net_output(net)

    crawls = route_crawls(crawl)
    routes = [src["route"] for src in crawls]
    sources = [src["source"] for src in crawls]
    svc_date = String(first(crawls)["service_date"])
    all(src -> src["service_date"] == svc_date, crawls) || error("Route snapshots must share a service date")
    dataset = length(crawls) == 1 ? String(first(routes)["route_short_name"]) : "network"
    haskey(FLEET_PROFILES, fleet_type) || error("Fleet type must be electric or conventional")
    profile = FLEET_PROFILES[fleet_type]
    energy_rate_kwh_per_km === nothing || energy_rate_kwh_per_km > 0 || error("Energy rate must be positive")
    fleet = isnothing(energy_rate_kwh_per_km) ? profile :
        (; profile..., energy_kwh_per_km=energy_rate_kwh_per_km,
           energy_reference="User-supplied energy rate")
    dist_path = joinpath(dirname(in_path), "distance_matrix_$(dataset).json")
    dist_mat = JSON3.read(read(dist_path, String))
    trip_energy_out = trip_energy(timetable_patterns, dist_mat, fleet)
    fleet_out = (;
        type=fleet_type,
        fleet...,
        distance_matrix=basename(dist_path),
        distance_source=String(dist_mat["metadata"]["source"]),
        distance_kind=String(dist_mat["metadata"]["distance_kind"]),
        distance_vehicle_access=String(dist_mat["metadata"]["vehicle_access"]),
    )
    cfg = (
        dataset=dataset,  # Public route number or short name.
        service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
        scenario="corridor_only",  # Scenario name, or corridor_only for the shared network.
        request_count=0,  # Total number of requests in this output.
        prebooked_count=0,  # Number of pre-booked requests.
        dynamic_count=0,  # Number of dynamic requests.
        # Allowed pickup deviation on either side of the desired time in minutes.
        pickup_window_half_width_minutes=PICKUP_HALF_WIDTH_MIN,
    )
    params = (
        # Corridor service start and end, measured in service-day minutes.
        operating_hours=[hrs.start_minute, hrs.end_minute],
        promise_window=(  # Early and late pickup allowances in minutes.
            early_minutes=PICKUP_HALF_WIDTH_MIN,  # Allowed minutes before the desired pickup time.
            late_minutes=PICKUP_HALF_WIDTH_MIN,  # Allowed minutes after the desired pickup time.
        ),
        # Definition of the service-day time axis used in the output.
        time_unit="minutes from service-day start; values may exceed 1440 for after-midnight trips",
        # Description of how scheduled travel times are aggregated.
        scheduled_travel_time_method="floor(median scheduled departure-to-arrival seconds / 60) over active trips",
        # Description of how stop dwell times are aggregated.
        dwell_time_method="zero; extracted stop arrivals and departures are equal",
    )
    meta = (
        title="Scheduled bus network",  # Readable title describing the dataset.
        routes=routes,  # Original GTFS route metadata.
        service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
        sources=sources,  # Source feed provenance copied from the crawler.
        # Explanation of direction-specific logical stop IDs.
        stop_mapping="Each pattern occurrence has a logical stop ID; network.source_stop_ids owns the physical-stop mapping.",
        fleet_data="Scenario files estimate scheduled-trip energy from OSRM road distances and a selected fleet rate; charging inputs are not included.",
    )
    corridor = (
        schema_version=2,  # Version of this output file format.
        config=cfg,  # Route, service date, and scenario settings.
        network=net_out,  # Shared logical network and scheduled travel times.
        # Requests grouped as prebooked and dynamic, empty for the corridor.
        requests=(prebooked=Dict(), dynamic=Dict()),
        parameters=params,  # Operating hours, pickup allowances, and time conventions.
        metadata=meta,  # Shared corridor provenance and scope notes.
    )
    write_json(joinpath(out_dir, "corridor_$(dataset).json"), corridor)

    timetable = (
        schema_version=2,  # Version of this output file format.
        routes=routes,  # Original GTFS route metadata.
        service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
        sources=sources,  # Source feed provenance copied from the crawler.
        operating_hours=hrs,  # Corridor service start and end, measured in service-day minutes.
        active_service_ids=unique([String(id) for src in crawls for id in src["active_service_ids"]]),  # GTFS service IDs active on the selected date.
        service_calendars=[src["service_calendar"] for src in crawls],  # Weekly GTFS service rules and date exceptions.
        network=net_out,  # Original GTFS stop records with names and coordinates.
        patterns=timetable_patterns,  # Pattern timetables containing original trip stop events.
    )
    write_json(joinpath(out_dir, "timetable_$(dataset).json"), timetable)

    cands = build_cand_pool(timetable_patterns, net)
    cand_meta = (
        # Description of the candidate sampling or scenario selection method.
        method="Julia-native pool sampled uniformly from feasible scheduled trip/stop pairs",
        seed=SEED,  # Random seed used to generate the candidate pool.
        # Number of candidates drawn for each booking-type/route/pattern cell.
        candidate_count_per_booking_route_pattern_cell=CAND_COUNT_PER_CELL,
        schema_version=2,
        candidate_pool=[(
            booking_type=book_type, route_id=pattern.route_id, pattern_id=pattern.pattern_id,
            candidates=[cand_output(cand, net) for cand in cands[(book_type, pattern.route_id, pattern.pattern_id)]],
        ) for pattern in net.patterns for book_type in ("prebooked", "dynamic")],
        lead_time_rules=(  # Configured minimum and maximum booking leads in minutes.
            # Minimum and maximum pre-booking leads converted from whole days.
            prebooked_minutes=[first(PREBOOK_LEAD_DAYS), last(PREBOOK_LEAD_DAYS)] .* 1440,
            # Minimum and maximum configured dynamic booking leads.
            dynamic_minutes=[first(DYN_LEAD_MIN), last(DYN_LEAD_MIN)],
        ),
        # Allowed pickup deviation on either side of the desired time in minutes.
        pickup_window_half_width_minutes=PICKUP_HALF_WIDTH_MIN,
    )
    write_json(joinpath(out_dir, "candidate_pool_$(dataset).json"), cand_meta)

    for (scen, total) in SCEN_REQ_COUNTS
        sel, allocs = select_instance_candidates(cands, total, net)
        reqs = requests_output(sel, net)
        prebook_count = length(reqs.prebooked)
        dyn_count = length(reqs.dynamic)
        inst_cfg = (;
            cfg...,  # Inherit route, service date, and pickup width from the corridor config.
            scenario=scen,  # Scenario name, or corridor_only for the shared network.
            fleet_type=fleet_type,  # User-selected electric or conventional bus profile.
            request_count=total,  # Total number of requests in this output.
            prebooked_count=prebook_count,  # Number of pre-booked requests.
            dynamic_count=dyn_count,  # Number of dynamic requests.
            route_pattern_booking_allocations=allocs,  # Request counts for each booking-type/route/pattern cell.
        )
        gen_meta = (
            # Description of the candidate sampling or scenario selection method.
            method="Seeded feasible scheduled trip/stop-pair pool; nested low/base/high samples",
            seed=SEED,  # Random seed used to generate the candidate pool.
            service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
            candidate_count_per_cell=CAND_COUNT_PER_CELL,  # Candidate pool size per booking-type/route/pattern cell.
            route_pattern_booking_allocations=allocs,  # Request counts for each booking-type/route/pattern cell.
            demand_is_observed=false,  # False because requests are synthetic rather than observed ridership.
        )
        inst = (
            schema_version=2,
            config=inst_cfg,  # Route, service date, and scenario settings.
            network=net_out,  # Shared logical network and scheduled travel times.
            fleet=fleet_out,  # Selected vehicle type and energy assumption.
            trip_energy=trip_energy_out,  # Each scheduled trip's estimated road distance and energy.
            requests=reqs,  # Final request records grouped by booking category.
            parameters=params,  # Operating hours, pickup allowances, and time conventions.
            generation=gen_meta,  # Scenario sampling settings and allocation metadata.
            metadata=corridor.metadata,  # Shared corridor provenance and scope notes.
        )
        inst_dir = fleet_type == "electric" ? joinpath(out_dir, "instances") : joinpath(out_dir, "instances", fleet_type)
        write_json(joinpath(inst_dir, "$(dataset)_$(scen).json"), inst)
        println("Wrote $(scen) scenario: $total requests ($(prebook_count) pre-booked, $(dyn_count) dynamic)")
    end

    println("Wrote corridor, timetable, candidate pool, and $(length(SCEN_REQ_COUNTS)) instances to $out_dir")
    println("Network has $(length(net_out.stops)) logical stops ($(length(net.mandatory_stops)) mandatory, $(length(net_out.optional_stops)) optional)")
end

# Optional paths retain their existing order; flags select the fleet assumptions.
if abspath(PROGRAM_FILE) == abspath(@__FILE__)
    if ARGS == ["--help"] || ARGS == ["-h"]
        println("Usage: julia --project=. src/reqreate_gen/generate.jl [in_path] [out_dir] [class_path] [--fleet-type=electric|conventional] [--energy-rate-kwh-per-km=NUMBER]")
        println("Defaults: $CRAWLED_PATH → $DATA_DIR")
    else
        pos_args = filter(arg -> !startswith(arg, "--"), ARGS)
        fleet_types = [String(split(arg, "="; limit=2)[2]) for arg in ARGS if startswith(arg, "--fleet-type=")]
        fleet_type = isempty(fleet_types) ? "electric" : only(fleet_types)
        energy_rates = [parse(Float64, split(arg, "="; limit=2)[2]) for arg in ARGS if startswith(arg, "--energy-rate-kwh-per-km=")]
        energy_rate = isempty(energy_rates) ? nothing : only(energy_rates)
        main(pos_args...; fleet_type=fleet_type, energy_rate_kwh_per_km=energy_rate)
    end
end
