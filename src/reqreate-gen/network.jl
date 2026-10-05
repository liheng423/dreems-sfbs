#=
Build direction-specific logical stops and scheduled travel-time matrices.

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
Return the logical network, pattern timetables, and operating hours from GTFS data and stop classes.

## NetworkData fields

- `directions`: Direction records with stop sequences and service windows.
- `mandatory_stops`: Logical IDs classified as mandatory by the stop configuration.
- `coordinates`: Logical ID → [longitude, latitude] in degrees.
- `stop_names`: Logical ID → original GTFS stop name.
- `source_stop_ids`: Logical ID → original GTFS stop ID.
- `travel_times`: "origin,destination" → median scheduled whole minutes for forward pairs.
- `dwell_times`: Logical ID → median scheduled dwell seconds floored to minutes.
- `class_reasons`: Logical ID → explanation of its mandatory or optional classification.

## Direction fields

- `direction_id`: GTFS direction ID: "0" toward Remich or "1" toward Bettembourg for Route 550.
- `pattern_id`: GTFS pattern ID grouping trips with the same stop sequence.
- `label`: Readable direction label.
- `stops`: Logical stop IDs in travel order, numbered separately per pattern.
- `service_period`: First departure through last arrival for this pattern.

## ServicePeriod fields

- `start_seconds`: First departure in seconds from service-day midnight.
- `end_seconds`: Last arrival in seconds from service-day midnight.
"""
function build_net(crawl, class_cfg)
    stops_by_src = Dict(String(stop["stop_id"]) => stop for stop in crawl["stops"])
    reason_by_src = Dict{String, String}(String(k) => String(v)
                                         for (k, v) in pairs(class_cfg["mandatory_stop_ids"]))
    dirs = Direction[]
    mand_ids = Int[]
    coords = Dict{String, Vector{Float64}}()
    stop_names = Dict{String, String}()
    src_ids_by_logi = Dict{String, String}()
    class_reasons = Dict{String, String}()
    dwell_samps = Dict{Int, Vector{Int}}()
    trav_samps = Dict{String, Vector{Int}}()
    timetable_pats = NamedTuple[]

    # A physical GTFS stop used by both directions receives one logical ID in
    # each pattern. This makes direction and scheduled travel-time lookup
    # explicit while preserving the source stop ID and coordinates.
    for (pat, dir) in zip(crawl["patterns"], build_dirs(crawl["patterns"]))
        src_ids = dir.source_stop_ids
        logi_ids = dir.stops
        for (src_id, logi_id) in zip(src_ids, logi_ids)
            src_stop = stops_by_src[src_id]
            coords[string(logi_id)] = Float64[src_stop["stop_lon"], src_stop["stop_lat"]]
            stop_names[string(logi_id)] = String(src_stop["stop_name"])
            src_ids_by_logi[string(logi_id)] = src_id
            if haskey(reason_by_src, src_id)
                push!(mand_ids, logi_id)
                class_reasons[string(logi_id)] = reason_by_src[src_id]
            else
                class_reasons[string(logi_id)] = "Optional: intermediate Route 550 stop; no mandatory locality-anchor or interchange role was assigned."
            end
        end

        for trip in pat["trips"]
            evts = trip["stop_times"]
            for idx in eachindex(evts)
                evt = evts[idx]
                stop_id = logi_ids[idx]
                dwell_sec = Int(evt["departure_seconds"] - evt["arrival_seconds"])
                push!(get!(dwell_samps, stop_id, Int[]), dwell_sec)
                for dst_idx in (idx + 1):length(evts)
                    dst_evt = evts[dst_idx]
                    trav_sec = Int(dst_evt["arrival_seconds"] - evt["departure_seconds"])
                    od = od_key(stop_id, logi_ids[dst_idx])
                    push!(get!(trav_samps, od, Int[]), trav_sec)
                end
            end
        end

        period = pat["service_period"]
        push!(dirs, Direction(
            dir.direction_id,
            dir.pattern_id,
            dir.label,
            logi_ids,
            ServicePeriod(
                Int(period["first_departure_seconds"]),
                Int(period["last_arrival_seconds"]),
            ),
        ))
        push!(timetable_pats, (
            pattern_id=dir.pattern_id,  # GTFS pattern ID for these trips.
            direction_id=dir.direction_id,  # GTFS direction ID for this pattern.
            label=dir.label,  # Readable direction label.
            source_stop_ids=src_ids,  # Original GTFS stop IDs in travel order.
            trips=pat["trips"],  # Original GTFS trips with their stop events.
        ))
    end

    trav_times = Dict{String, Int}(od => med_min(samps)
                                   for (od, samps) in trav_samps)
    dwell_times = Dict{String, Int}(string(id) => med_min(samps)
                                    for (id, samps) in dwell_samps)
    first_min = Int(crawl["operating_hours"]["start_minute"])
    last_min = Int(crawl["operating_hours"]["end_minute"])
    net = NetworkData(
        dirs,
        mand_ids,
        coords,
        stop_names,
        src_ids_by_logi,
        trav_times,
        dwell_times,
        class_reasons,
    )
    return (
        net,  # Logical network with stop classes and scheduled travel times.
        timetable_pats,  # Pattern records retaining the original GTFS trips.
        (
            start_minute=first_min,  # Corridor service start in service-day minutes.
            end_minute=last_min,  # Corridor service end in service-day minutes.
        ),  # Corridor-wide operating hours.
    )
end
