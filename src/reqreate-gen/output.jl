"""
Reconstruct derived network fields when writing the existing JSON schema.

- `stops`: All logical IDs flattened from the direction stop sequences.
- `optional_stops`: Logical IDs not present in mandatory_stops.
- `terminals`: First and last logical stop IDs of every direction.
- `directions[].source_stop_ids`: Original IDs resolved through the network map.
- `directions[].terminal_ids`: First and last IDs of the direction's stops.
- `service_period.start_minute`: First departure seconds rounded down to minutes.
- `service_period.end_minute`: Last arrival seconds rounded up to minutes.
"""
function net_output(net::NetworkData)
    stop_ids = [stop_id for dir in net.directions for stop_id in dir.stops]
    dirs = [(
        direction_id=dir.direction_id,
        pattern_id=dir.pattern_id,
        label=dir.label,
        stops=dir.stops,
        source_stop_ids=[net.source_stop_ids[string(id)] for id in dir.stops],
        terminal_ids=[first(dir.stops), last(dir.stops)],
        service_period=(
            start_minute=s2m(dir.service_period.start_seconds),
            end_minute=cld(dir.service_period.end_seconds, 60),
            start_seconds=dir.service_period.start_seconds,
            end_seconds=dir.service_period.end_seconds,
        ),
    ) for dir in net.directions]
    return (
        stops=stop_ids,
        directions=dirs,
        mandatory_stops=net.mandatory_stops,
        optional_stops=setdiff(stop_ids, net.mandatory_stops),
        terminals=[id for dir in dirs for id in dir.terminal_ids],
        coordinates=net.coordinates,
        stop_names=net.stop_names,
        source_stop_ids=net.source_stop_ids,
        travel_times=net.travel_times,
        dwell_times=net.dwell_times,
        class_reasons=net.class_reasons,
    )
end

"""
Expand a selected request with derived fields for the existing scenario JSON schema.

- `direction`: Direction containing the origin logical stop.
- `time_window`: Desired pickup time plus/minus the configured half-width in minutes.
"""
function req_output(req::Request, net::NetworkData)
    return (
        id=req.id,
        type=req.type,
        origin=req.origin,
        destination=req.destination,
        desired_time=req.desired_time,
        time_window=pickup_window(req.desired_time),
        request_time=req.request_time,
        direction=stop_dir(net, req.origin).direction_id,
    )
end

"""
Expand a candidate with network-derived fields for the existing pool JSON schema.

- `direction_id`: Direction containing the origin logical stop.
- `time_window`: Desired pickup time plus/minus the configured half-width in minutes.
- `source_origin_stop_id`: Original GTFS origin ID resolved through the network map.
- `source_destination_stop_id`: Original GTFS destination ID resolved through the network map.
"""
function cand_output(cand::Candidate, net::NetworkData)
    return (
        candidate_id=cand.candidate_id,
        origin=cand.origin,
        destination=cand.destination,
        direction_id=stop_dir(net, cand.origin).direction_id,
        booking_type=cand.booking_type,
        desired_time=cand.desired_time,
        request_time=cand.request_time,
        time_window=pickup_window(cand.desired_time),
        source_trip_id=cand.source_trip_id,
        source_origin_stop_id=net.source_stop_ids[string(cand.origin)],
        source_destination_stop_id=net.source_stop_ids[string(cand.destination)],
        scheduled_arrival_minute=cand.scheduled_arrival_minute,
    )
end
