#!/usr/bin/env julia

#=
Build a directed-route network, scheduled-time matrix, and demand scenarios.

The command consumes normalized GTFS JSON from the Python crawler. It writes
the corridor, full trip timetable, candidate pool, and low/base/high JSON
instances. Passenger requests are synthetic scenario assumptions, not
observed ridership.

# Arguments

- `in_path`: normalized crawler JSON input (defaults to `data/crawled_550.json`).
- `out_dir`: directory for generated files (defaults to `data/`).
- `class_path`: source-stop classification JSON (defaults to Route 550 classes).
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

include("routes.jl")
include(joinpath("input_adapters", "network.jl"))
include(joinpath("demand_generators", "eligibility.jl"))
include(joinpath("demand_generators", "allocations.jl"))
include(joinpath("demand_generators", "demand.jl"))
include(joinpath("output_adapters", "output.jl"))

"""
Read GTFS from in_path and write the corridor, timetable, candidate pool, and scenarios to out_dir.
"""
function main(in_path::String=CRAWLED_PATH, out_dir::String=DATA_DIR, class_path::String=CLASS_PATH)
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
    cfg = (
        dataset=dataset,  # Public route number or short name.
        service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
        scenario="corridor_only",  # Scenario name, or corridor_only for the shared network.
        prebooked_share=PREBOOK_SHARE,
        electric_share=ELECTRIC_SHARE,
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
        # Configured service dwell; independent of the source timetable.
        dwell_time_method="uniform configured service dwell: $(DWELL_MIN) minutes per stop",
    )
    meta = (
        title="Scheduled bus network",  # Readable title describing the dataset.
        routes=routes,  # Original GTFS route metadata.
        service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
        sources=sources,  # Source feed provenance copied from the crawler.
        # Explanation of direction-specific logical stop IDs.
        stop_mapping="Each pattern occurrence has a logical stop ID; network.source_stop_ids owns the physical-stop mapping.",
        # Statement that fleet and charging inputs are outside this dataset.
        fleet_data="Not included; vehicle and charging inputs are a separate extension.",
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

    debug_rejected = DEBUG ? Candidate[] : nothing
    cands = build_cand_pool(net; debug_rejected)
    debug_path = joinpath(out_dir, "debug", "rejected_candidates_$(dataset).debug.json")
    debug_allocs = NamedTuple[]
    cand_meta = (
        # Description of the candidate sampling or scenario selection method.
        method="Independent stop and normal pickup-time draws filtered by mandatory-corridor timing",
        seed=SEED,  # Random seed used to generate the candidate pool.
        # Number of raw attempts per route pattern.
        candidate_attempts_per_pattern=CAND_COUNT_PER_PATTERN,
        schema_version=2,
        candidate_pool=[(
            route_id=pattern.route_id, pattern_id=pattern.pattern_id,
            candidates=[cand_output(cand, net) for cand in cands[(pattern.route_id, pattern.pattern_id)]],
        ) for pattern in net.patterns],
        pickup_distribution=(family="normal", mean_service_fraction=DES_MEAN_FRACTION,
            std_service_fraction=DES_STD_FRACTION),
        terminal_buffer_minutes=TERM_BUFFER_MIN,
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
        scen_rejected = DEBUG ? NamedTuple[] : nothing
        sel, allocs = select_instance_candidates(cands, total, net; debug_rejected=scen_rejected)
        if DEBUG
            append!(debug_allocs, [(; cand_output(row.candidate, net)...,
                scenario=scen, booking_type=row.booking_type, request_time=row.request_time,
                rejection_reasons=["booking_before_service_start"],
                service_start_minute=s2m(stop_pattern(net, row.candidate.origin).service_period.start_seconds))
                for row in scen_rejected])
        end
        reqs = requests_output(sel, net)
        prebook_count = length(reqs.prebooked)
        dyn_count = length(reqs.dynamic)
        inst_cfg = (;
            cfg...,  # Inherit route, service date, and pickup width from the corridor config.
            scenario=scen,  # Scenario name, or corridor_only for the shared network.
            request_count=total,  # Total number of requests in this output.
            prebooked_count=prebook_count,  # Number of pre-booked requests.
            dynamic_count=dyn_count,
            electric_count=count(req -> req.bus_type == "electric",
                Iterators.flatten((values(reqs.prebooked), values(reqs.dynamic)))),
            conventional_count=count(req -> req.bus_type == "conventional",
                Iterators.flatten((values(reqs.prebooked), values(reqs.dynamic)))),  # Number of dynamic requests.
            route_pattern_booking_allocations=allocs,  # Request counts for each route pattern.
        )
        gen_meta = (
            # Description of the candidate sampling or scenario selection method.
            method="Seeded passenger preferences filtered by corridor timing; nested low/base/high samples",
            seed=SEED,  # Random seed used to generate the candidate pool.
            service_date=svc_date,  # GTFS service date in YYYY-MM-DD form.
            candidate_attempts_per_pattern=CAND_COUNT_PER_PATTERN,  # Raw attempts per route pattern.
            route_pattern_booking_allocations=allocs,  # Request counts for each route pattern.
            demand_is_observed=false,  # False because requests are synthetic rather than observed ridership.
        )
        inst = (
            schema_version=2,
            config=inst_cfg,  # Route, service date, and scenario settings.
            network=net_out,  # Shared logical network and scheduled travel times.
            requests=reqs,  # Final request records grouped by booking category.
            parameters=params,  # Operating hours, pickup allowances, and time conventions.
            generation=gen_meta,  # Scenario sampling settings and allocation metadata.
            metadata=corridor.metadata,  # Shared corridor provenance and scope notes.
        )
        write_json(joinpath(out_dir, "instances", "$(dataset)_$(scen).json"), inst)
        println("Wrote $(scen) scenario: $total requests ($(prebook_count) pre-booked, $(dyn_count) dynamic)")
    end

    if DEBUG
        write_json(debug_path, (
            debug=true, description="Rejected preferences and booking assignments; not scenario input.",
            seed=SEED, service_date=svc_date,
            candidate_attempts_per_pattern=CAND_COUNT_PER_PATTERN,
            rejected_count=length(debug_rejected),
            rejected_candidates=[rejected_cand_output(cand, net) for cand in debug_rejected],
            rejected_allocation_count=length(debug_allocs),
            rejected_allocations=debug_allocs,
        ))
    elseif isfile(debug_path)
        rm(debug_path) # Remove stale debug output for this dataset.
    end

    println("Wrote corridor, timetable, candidate pool, and $(length(SCEN_REQ_COUNTS)) instances to $out_dir")
    println("Network has $(length(net_out.stops)) logical stops ($(length(net.mandatory_stops)) mandatory, $(length(net_out.optional_stops)) optional)")
end

# Three optional paths are sufficient for this script's command-line interface.
if abspath(PROGRAM_FILE) == abspath(@__FILE__)
    if ARGS == ["--help"] || ARGS == ["-h"]
        println("Usage: julia --project=. src/reqreate_gen/generate.jl [in_path] [out_dir] [class_path]")
        println("Defaults: $CRAWLED_PATH → $DATA_DIR")
    else
        main(ARGS...)
    end
end
