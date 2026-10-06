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
    stop_ids = [stop_id for net_pat in net.patterns for stop_id in net_pat.stops]
    pats = [(
        route_id=net_pat.route_id,
        source_route_id=net_pat.source_route_id,
        source_direction_id=net_pat.source_direction_id,
        pattern_id=net_pat.pattern_id,
        label=net_pat.label,
        stops=net_pat.stops,
        terminal_ids=[first(net_pat.stops), last(net_pat.stops)],
        service_period=(
            start_minute=s2m(net_pat.service_period.start_seconds),
            end_minute=cld(net_pat.service_period.end_seconds, 60),
            start_seconds=net_pat.service_period.start_seconds,
            end_seconds=net_pat.service_period.end_seconds,
        ),
    ) for net_pat in net.patterns]
    route_groups = [[pat for pat in net.patterns if pat.route_id == route_id]
                    for route_id in unique(pat.route_id for pat in net.patterns)]
    return (
        stops=stop_ids,
        routes=[(
            route_id=first(group).route_id,
            source_route_id=first(group).source_route_id,
            source_direction_id=first(group).source_direction_id,
            pattern_ids=[pat.pattern_id for pat in group],
        ) for group in route_groups],
        patterns=pats,
        mandatory_stops=net.mandatory_stops,
        optional_stops=setdiff(stop_ids, net.mandatory_stops),
        terminals=[id for net_pat in pats for id in net_pat.terminal_ids],
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
"""
function cand_output(cand::Candidate, net::NetworkData)
    return (
        candidate_id=cand.candidate_id,
        origin=cand.origin,
        destination=cand.destination,
        route_id=stop_pat(net, cand.origin).route_id,
        pattern_id=stop_pat(net, cand.origin).pattern_id,
        booking_type=cand.booking_type,
        desired_time=cand.desired_time,
        request_time=cand.request_time,
        time_window=pickup_window(cand.desired_time),
        source_trip_id=cand.source_trip_id,
        source_origin_stop_id=src_stop_id(net, cand.origin),
        source_destination_stop_id=src_stop_id(net, cand.destination),
        scheduled_arrival_minute=cand.scheduled_arrival_minute,
    )
end
