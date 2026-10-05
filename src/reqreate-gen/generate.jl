#!/usr/bin/env julia

#=
Build the Route 550 corridor, scheduled-time matrix, and demand scenarios.

The command consumes normalized GTFS JSON from the Python crawler. It writes
the corridor, full trip timetable, candidate pool, and low/base/high JSON
instances. Passenger requests are synthetic scenario assumptions, not
observed ridership.

# Arguments

- `in_path`: normalized crawler JSON input (defaults to `data/crawled_550.json`).
- `out_dir`: directory for generated files (defaults to `data/`).
=#
using JSON3

include("types.jl")
include("demand_config.jl")

const SCRIPT_DIR = @__DIR__
const PROJECT_ROOT = dirname(dirname(SCRIPT_DIR))
const DATA_DIR = joinpath(PROJECT_ROOT, "data")
const CRAWLED_PATH = joinpath(DATA_DIR, "crawled_550.json")
const CLASS_PATH = joinpath(SCRIPT_DIR, "stop_classes_550.json")

include(joinpath(@__DIR__, "..", "utilities", "utilities.jl"))

include("directions.jl")
include("network.jl")
include("demand.jl")
include("output.jl")

"""
Read GTFS from in_path and write the corridor, timetable, candidate pool, and scenarios to out_dir.

## RequestGroups fields

- `prebooked`: Request ID → pre-booked request.
- `dynamic`: Request ID → dynamic request.
"""
function main(in_path::String=CRAWLED_PATH, out_dir::String=DATA_DIR)
    in_path = abspath(in_path)
    out_dir = abspath(out_dir)
    crawl = JSON3.read(read(in_path, String))
    class_cfg = JSON3.read(read(CLASS_PATH, String))
    net, timetable_pats, hrs = build_net(crawl, class_cfg)
    net_out = net_output(net)

    route = asdict(crawl["route"])
    src = asdict(crawl["source"])
    svc_date = String(crawl["service_date"])
    cfg = (
        route_short_name=String(route["route_short_name"]),  # Public route number or short name.
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
        dwell_time_method="floor(median GTFS departure-minus-arrival seconds / 60) at each logical stop",
    )
    meta = (
        title="Route 550 scheduled corridor",  # Readable title describing the dataset.
        route=route,  # Original GTFS route metadata.
        service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
        source=src,  # Source feed provenance copied from the crawler.
        # Explanation of direction-specific logical stop IDs.
        direction_patterns="Each direction has distinct logical stop IDs, even at shared physical stops.",
        # Statement that fleet and charging inputs are outside this dataset.
        fleet_data="Not included; vehicle and charging inputs are a separate extension.",
    )
    corridor = (
        schema_version=1,  # Version of this output file format.
        config=cfg,  # Route, service date, and scenario settings.
        network=net_out,  # Shared logical network and scheduled travel times.
        # Requests grouped as prebooked and dynamic, empty for the corridor.
        requests=RequestGroups(
            Dict{String, Request}(),
            Dict{String, Request}(),
        ),
        parameters=params,  # Operating hours, pickup allowances, and time conventions.
        metadata=meta,  # Shared corridor provenance and scope notes.
    )
    write_json(joinpath(out_dir, "corridor_550.json"), corridor)

    timetable = (
        schema_version=1,  # Version of this output file format.
        route=route,  # Original GTFS route metadata.
        service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
        source=src,  # Source feed provenance copied from the crawler.
        operating_hours=hrs,  # Corridor service start and end, measured in service-day minutes.
        active_service_ids=String.(crawl["active_service_ids"]),  # GTFS service IDs active on the selected date.
        service_calendar=crawl["service_calendar"],  # Weekly GTFS service rules and date exceptions.
        stops=crawl["stops"],  # Original GTFS stop records with names and coordinates.
        patterns=timetable_pats,  # Pattern timetables containing original trip stop events.
    )
    write_json(joinpath(out_dir, "timetable_550.json"), timetable)

    cands = build_cand_pool(crawl, net)
    cand_meta = (
        # Description of the candidate sampling or scenario selection method.
        method="Julia-native pool sampled uniformly from feasible scheduled trip/stop pairs",
        seed=SEED,  # Random seed used to generate the candidate pool.
        # Number of candidates drawn for each booking-type/direction cell.
        candidate_count_per_booking_direction_cell=CAND_COUNT_PER_CELL,
        candidate_pool=Dict(key => [cand_output(cand, net) for cand in cell] for (key, cell) in cands),  # Cell key → shuffled candidate request array.
        lead_time_rules=(  # Configured minimum and maximum booking leads in minutes.
            # Minimum and maximum pre-booking leads converted from whole days.
            prebooked_minutes=[first(PREBOOK_LEAD_DAYS), last(PREBOOK_LEAD_DAYS)] .* 1440,
            # Minimum and maximum configured dynamic booking leads.
            dynamic_minutes=[first(DYN_LEAD_MIN), last(DYN_LEAD_MIN)],
        ),
        # Allowed pickup deviation on either side of the desired time in minutes.
        pickup_window_half_width_minutes=PICKUP_HALF_WIDTH_MIN,
    )
    write_json(joinpath(out_dir, "candidate_pool_550.json"), cand_meta)

    for (scen, total) in SCEN_REQ_COUNTS
        reqs, allocs = inst_reqs(cands, total, net)
        prebook_count = length(reqs.prebooked)
        dyn_count = length(reqs.dynamic)
        inst_cfg = (;
            cfg...,  # Inherit route, service date, and pickup width from the corridor config.
            scenario=scen,  # Scenario name, or corridor_only for the shared network.
            request_count=total,  # Total number of requests in this output.
            prebooked_count=prebook_count,  # Number of pre-booked requests.
            dynamic_count=dyn_count,  # Number of dynamic requests.
            direction_booking_allocations=allocs,  # Request counts for each booking-type/direction cell.
        )
        gen_meta = (
            # Description of the candidate sampling or scenario selection method.
            method="Seeded feasible scheduled trip/stop-pair pool; nested low/base/high samples",
            seed=SEED,  # Random seed used to generate the candidate pool.
            service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
            candidate_count_per_cell=CAND_COUNT_PER_CELL,  # Candidate pool size per booking-type/direction cell.
            direction_booking_allocations=allocs,  # Request counts for each booking-type/direction cell.
            demand_is_observed=false,  # False because requests are synthetic rather than observed ridership.
        )
        inst = (
            config=inst_cfg,  # Route, service date, and scenario settings.
            network=net_out,  # Shared logical network and scheduled travel times.
            requests=(  # Expand derived request fields only for output.
                prebooked=Dict(id => req_output(req, net) for (id, req) in reqs.prebooked),
                dynamic=Dict(id => req_output(req, net) for (id, req) in reqs.dynamic),
            ),
            parameters=params,  # Operating hours, pickup allowances, and time conventions.
            generation=gen_meta,  # Scenario sampling settings and allocation metadata.
            metadata=corridor.metadata,  # Shared corridor provenance and scope notes.
        )
        write_json(joinpath(out_dir, "instances", "550_$(scen).json"), inst)
        println("Wrote $(scen) scenario: $total requests ($(prebook_count) pre-booked, $(dyn_count) dynamic)")
    end

    println("Wrote corridor, timetable, candidate pool, and $(length(SCEN_REQ_COUNTS)) instances to $out_dir")
    println("Network has $(length(net_out.stops)) logical stops ($(length(net.mandatory_stops)) mandatory, $(length(net_out.optional_stops)) optional)")
end

# Two optional paths are sufficient for this script's command-line interface.
if abspath(PROGRAM_FILE) == abspath(@__FILE__)
    if ARGS == ["--help"] || ARGS == ["-h"]
        println("Usage: julia --project=. src/reqreate-gen/generate.jl [in_path] [out_dir]")
        println("Defaults: $CRAWLED_PATH → $DATA_DIR")
    else
        main(ARGS...)
    end
end
