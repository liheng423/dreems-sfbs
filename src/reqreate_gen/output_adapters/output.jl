"""
Reconstruct derived network fields when writing the network JSON schema.

- `stops`: All logical IDs flattened from the pattern stop sequences.
- `optional_stops`: Logical IDs not present in mandatory_stops.
- `terminals`: First and last logical stop IDs of every pattern.
- `patterns[].terminal_ids`: First and last IDs of the pattern's stops.
- `service_period.start_minute`: First departure seconds rounded down to minutes.
- `service_period.end_minute`: Last arrival seconds rounded up to minutes.
"""
function net_output(net::NetworkData)
    stop_ids = [stop_id for net_pattern in net.patterns for stop_id in net_pattern.stops]
    patterns = [(
        route_id=net_pattern.route_id,
        source_route_id=net_pattern.source_route_id,
        source_direction_id=net_pattern.source_direction_id,
        pattern_id=net_pattern.pattern_id,
        label=net_pattern.label,
        stops=net_pattern.stops,
        terminal_ids=[first(net_pattern.stops), last(net_pattern.stops)],
        service_period=(
            start_minute=s2m(net_pattern.service_period.start_seconds),
            end_minute=cld(net_pattern.service_period.end_seconds, 60),
            start_seconds=net_pattern.service_period.start_seconds,
            end_seconds=net_pattern.service_period.end_seconds,
        ),
    ) for net_pattern in net.patterns]
    route_groups = [[pattern for pattern in net.patterns if pattern.route_id == route_id]
                    for route_id in unique(pattern.route_id for pattern in net.patterns)]
    return (
        stops=stop_ids,
        routes=[(
            route_id=first(group).route_id,
            source_route_id=first(group).source_route_id,
            source_direction_id=first(group).source_direction_id,
            pattern_ids=[pattern.pattern_id for pattern in group],
        ) for group in route_groups],
        patterns=patterns,
        mandatory_stops=net.mandatory_stops,
        optional_stops=setdiff(stop_ids, net.mandatory_stops),
        terminals=[id for net_pattern in patterns for id in net_pattern.terminal_ids],
        coordinates=net.coordinates,
        stop_names=net.stop_names,
        source_stop_ids=net.source_stop_ids,
        travel_times=net.travel_times,
        dwell_times=net.dwell_times,
        class_reasons=net.class_reasons,
    )
end

"""
Expand a candidate with network-derived fields for the pool JSON schema.

- `route_id`, `pattern_id`: Directed route and pattern owning the origin.
- `time_window`: Desired pickup time plus/minus the configured half-width in minutes.
- `source_origin_stop_id`: Original GTFS origin ID resolved through the network map.
- `source_destination_stop_id`: Original GTFS destination ID resolved through the network map.
- `scheduled_arrival_minute`: Existing JSON field for the source trip's destination departure minute.
"""
function cand_output(cand::Candidate, net::NetworkData)
    return (
        candidate_id=cand.candidate_id,
        origin=cand.origin,
        destination=cand.destination,
        route_id=stop_pattern(net, cand.origin).route_id,
        pattern_id=stop_pattern(net, cand.origin).pattern_id,
        booking_type=cand.booking_type,
        desired_time=cand.desired_time,
        request_time=cand.request_time,
        time_window=pickup_window(cand.desired_time),
        source_trip_id=cand.source_trip_id,
        source_origin_stop_id=src_stop_id(net, cand.origin),
        source_destination_stop_id=src_stop_id(net, cand.destination),
        scheduled_arrival_minute=cand.destination_departure_minute,
    )
end

"""
    requests_output(sel, net)

Build the scenario JSON request groups from candidates sorted by booking time.
Request IDs start at zero and span both booking types.

# Arguments
- `sel`: Selected candidates in request ID order.
- `net`: NetworkData used to find each candidate's route and pattern.

# Returns
- Named tuple with `prebooked` and `dynamic` dictionaries keyed by string request ID.
"""
function requests_output(sel::Vector{Candidate}, net::NetworkData)
    reqs = (prebooked=Dict{String, NamedTuple}(), dynamic=Dict{String, NamedTuple}())
    for (req_idx, cand) in enumerate(sel)
        book_type = cand.booking_type
        req_id = req_idx - 1
        req = (
            id=req_id,
            type=book_type,
            origin=cand.origin,
            destination=cand.destination,
            desired_time=cand.desired_time,
            time_window=pickup_window(cand.desired_time),
            request_time=cand.request_time,
            route_id=stop_pattern(net, cand.origin).route_id,
            pattern_id=stop_pattern(net, cand.origin).pattern_id,
        )
        req_map = book_type == "prebooked" ? reqs.prebooked : reqs.dynamic
        req_map[string(req_id)] = req
    end
    return reqs
end

"""
    pickup_window(des_min)

Compute the inclusive pickup window around a desired service-day minute.

# Arguments
- `des_min`: Desired pickup minute from the service-day start.

# Returns
- Two-element vector: Earliest and latest pickup minutes, each `PICKUP_HALF_WIDTH_MIN` from `des_min`.
"""
pickup_window(des_min) = [des_min - PICKUP_HALF_WIDTH_MIN, des_min + PICKUP_HALF_WIDTH_MIN]
