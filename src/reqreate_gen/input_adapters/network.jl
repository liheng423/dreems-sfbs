#=
Build pattern-specific logical stops and scheduled travel-time matrices.

Included by `generate.jl`; functions share its route data structures.
=#

using Statistics

"""Return the median of second-based samples, rounded down to whole minutes."""
function med_min(vals::Vector{Int})
    # The network matrix uses one representative scheduled duration per pair.
    # Flooring matches the KU Leuven whole-minute convention.
    return floor(Int, median(vals) / 60)
end

"""
    build_net(crawl, class_cfg; dwell_min=DWELL_MIN)

Build pattern-specific logical stops, stop classes, and median scheduled travel
times from normalized GTFS data.

# Arguments
- `crawl`: One normalized route snapshot or a vector of route snapshots.
- `dwell_min`: Uniform modeled stop dwell in whole minutes, from configuration by default.
- `class_cfg`: Stop classification with `mandatory_stop_ids` mapping source stop IDs to reasons.

# Returns
- `net`: `NetworkData` with logical routes and stops, classifications, and travel times.
- `timetable_patterns`: Pattern records with logical stop IDs and original GTFS trips.
- `hrs`: Named tuple with `start_minute` and `end_minute` for corridor-wide service hours.
"""
function build_net(crawl, class_cfg; dwell_min::Int=DWELL_MIN)
    crawls = route_crawls(crawl)
    stops_by_src = Dict(String(stop["stop_id"]) => stop for src in crawls for stop in src["stops"])
    reason_by_src = Dict{String, String}(String(k) => String(v)
                                         for (k, v) in pairs(class_cfg["mandatory_stop_ids"]))
    patterns = RoutePattern[]
    next_logi_id = 1
    mand_ids = Int[]
    coords = Dict{String, Vector{Float64}}()
    stop_names = Dict{String, String}()
    src_ids_by_logi = Dict{String, String}()
    class_reasons = Dict{String, String}()
    trav_samps = Dict{String, Vector{Int}}()
    timetable_patterns = NamedTuple[]

    # A physical GTFS stop used by both directions receives one logical ID in
    # each pattern. This makes direction and scheduled travel-time lookup
    # explicit while preserving the source stop ID and coordinates.
    for src in crawls, pattern in src["patterns"]
        src_route_id = String(src["route"]["route_id"])
        src_dir_id = String(pattern["direction_id"])
        route_id = "$(src_route_id)_$(src_dir_id)"
        src_ids = String.(pattern["stop_ids"])
        logi_ids = collect(next_logi_id:(next_logi_id + length(src_ids) - 1))
        next_logi_id += length(src_ids)
        for (src_id, logi_id) in zip(src_ids, logi_ids)
            src_stop = stops_by_src[src_id]
            coords[string(logi_id)] = Float64[src_stop["stop_lon"], src_stop["stop_lat"]]
            stop_names[string(logi_id)] = String(src_stop["stop_name"])
            src_ids_by_logi[string(logi_id)] = src_id
            if haskey(reason_by_src, src_id)
                push!(mand_ids, logi_id)
                class_reasons[string(logi_id)] = reason_by_src[src_id]
            elseif logi_id == first(logi_ids) || logi_id == last(logi_ids)
                push!(mand_ids, logi_id)
                class_reasons[string(logi_id)] = "Mandatory: terminal of a directed route pattern."
            else
                class_reasons[string(logi_id)] = "Optional: intermediate stop; no mandatory locality-anchor or interchange role was assigned."
            end
        end

        for trip in pattern["trips"]
            evts = trip["stop_times"]
            for idx in eachindex(evts)
                evt = evts[idx]
                stop_id = logi_ids[idx]
                for dst_idx in (idx + 1):length(evts)
                    dst_evt = evts[dst_idx]
                    trav_sec = Int(dst_evt["departure_seconds"] - evt["departure_seconds"])
                    od = od_key(stop_id, logi_ids[dst_idx])
                    push!(get!(trav_samps, od, Int[]), trav_sec)
                end
            end
        end

        period = pattern["service_period"]
        push!(patterns, RoutePattern(
            route_id,
            String(pattern["pattern_id"]),
            logi_ids,
            ServicePeriod(
                Int(period["first_departure_seconds"]),
                Int(period["last_arrival_seconds"]),
            ),
            src_route_id,
            src_dir_id,
            String(pattern["label"]),
        ))
        push!(timetable_patterns, (
            route_id=route_id,
            pattern_id=String(pattern["pattern_id"]),
            stops=logi_ids,  # Source IDs are resolved through the network.
            trips=pattern["trips"],  # Original GTFS trips with their stop events.
        ))
    end

    trav_times = Dict{String, Int}(od => med_min(samps)
                                   for (od, samps) in trav_samps)
    dwell_times = Dict(string(id) => dwell_min for pattern in patterns for id in pattern.stops)
    first_min = minimum(s2m(pattern.service_period.start_seconds) for pattern in patterns)
    last_min = maximum(cld(pattern.service_period.end_seconds, 60) for pattern in patterns)
    net = NetworkData(
        patterns,
        trav_times,
        mand_ids,
        coords,
        stop_names,
        src_ids_by_logi,
        dwell_times,
        class_reasons,
    )
    return (
        net,  # Logical network with stop classes and scheduled travel times.
        timetable_patterns,  # Pattern records retaining the original GTFS trips.
        (
            start_minute=first_min,  # Corridor service start in service-day minutes.
            end_minute=last_min,  # Corridor service end in service-day minutes.
        ),  # Corridor-wide operating hours.
    )
end
