#=
Sample seeded passenger demand from feasible Route 550 timetable pairs.

Included by `generate.jl`; settings are defined in `demand_config.jl`.
=#

using Random

"""
List trip/stop pairs whose pickup windows and scheduled journeys fit the direction timetable.

## SchedPair fields

- `org`: Origin logical stop ID.
- `dst`: Destination logical stop ID after the origin.
- `des_min`: Scheduled pickup time in whole service-day minutes.
- `sched_arr_min`: Scheduled destination arrival in whole service-day minutes.
- `src_trip_id`: Original GTFS trip ID supplying this pair.
"""
function elig_sched_pairs(pat, dir::Direction, net::NetworkData)
    logi_stops = dir.stops
    start_min = s2m(dir.service_period.start_seconds)
    end_min = cld(dir.service_period.end_seconds, 60)
    sched_pairs = SchedPair[]

    # Each eligible trip/OD combination contributes one sampling opportunity.
    # Frequencies in the timetable therefore shape the desired-time profile.
    for trip in pat["trips"]
        evts = trip["stop_times"]
        for org_idx in 1:(length(logi_stops) - 1)
            org = logi_stops[org_idx]
            des_min = s2m(Int(evts[org_idx]["departure_seconds"]))
            for dst_idx in (org_idx + 1):length(logi_stops)
                dst = logi_stops[dst_idx]
                arr_min = s2m(Int(evts[dst_idx]["arrival_seconds"]))
                dur_min = net.travel_times[od_key(org, dst)]
                if des_min - PICKUP_HALF_WIDTH_MIN < start_min ||
                   des_min + dur_min > arr_min ||
                   des_min + PICKUP_HALF_WIDTH_MIN > end_min
                    continue
                end
                push!(sched_pairs, SchedPair(
                    org,
                    dst,
                    des_min,
                    arr_min,
                    String(trip["trip_id"]),
                ))
            end
        end
    end
    return sched_pairs
end

"""
Sample and shuffle seeded candidate requests for each booking type and direction.

## Candidate fields

- `candidate_id`: Unique booking-type_direction_index identifier within the candidate pool.
- `origin`: Origin logical stop ID.
- `destination`: Destination logical stop ID.
- `booking_type`: Booking category: "prebooked" or "dynamic".
- `desired_time`: Desired pickup time in service-day minutes.
- `request_time`: Booking submission time in service-day minutes, possibly negative.
- `source_trip_id`: Original GTFS trip ID used to generate the candidate.
- `scheduled_arrival_minute`: Source trip's destination arrival in whole service-day minutes.
"""
function build_cand_pool(crawl, net; seed::Int=SEED)
    rng = MersenneTwister(seed)
    cands = Dict{String, Vector{Candidate}}()
    pats = Dict(String(pat["pattern_id"]) => pat for pat in crawl["patterns"])
    for dir in net.directions
        dir_id = dir.direction_id
        pat = pats[dir.pattern_id]
        sched_pairs = elig_sched_pairs(pat, dir, net)
        start_min = s2m(dir.service_period.start_seconds)
        for book_type in ("prebooked", "dynamic")
            # Booking lead and pickup width are independently configurable.
            # Dynamic pairs need enough lead time after service starts.
            elig_pairs = book_type == "dynamic" ?
                filter(pair -> pair.des_min - start_min >= first(DYN_LEAD_MIN), sched_pairs) : sched_pairs
            cand_cell = Candidate[]
            for cand_idx in 1:CAND_COUNT_PER_CELL
                pair = rand(rng, elig_pairs)
                max_lead = min(last(DYN_LEAD_MIN), pair.des_min - start_min)
                lead = book_type == "prebooked" ?
                    rand(rng, PREBOOK_LEAD_DAYS) * 1440 : rand(rng, first(DYN_LEAD_MIN):max_lead)
                des_min = pair.des_min
                push!(cand_cell, Candidate(
                    "$(book_type)_$(dir_id)_$(cand_idx)",
                    pair.org,
                    pair.dst,
                    book_type,
                    des_min,
                    des_min - lead,
                    pair.src_trip_id,
                    pair.sched_arr_min,
                ))
            end
            shuffle!(rng, cand_cell)
            cands["$(book_type)_$(dir_id)"] = cand_cell
        end
    end
    return cands
end

"""Split an even request total equally across booking types and directions 0/1."""
function scen_allocs(total::Int)
    # Request totals are even. The 50-request case has four cells with two
    # half-cell remainders; put them on opposite booking types per direction.
    half = total ÷ 2
    base = half ÷ 2
    remainder = half % 2
    return (
        prebooked_0=base + remainder,  # Pre-booked request count in direction 0.
        prebooked_1=base,  # Pre-booked request count in direction 1.
        dynamic_0=base,  # Dynamic request count in direction 0.
        dynamic_1=base + remainder,  # Dynamic request count in direction 1.
    )
end

"""
Return numbered scenario requests and cell allocations from prefixes of the candidate pool.

## RequestGroups fields

- `prebooked`: Request ID → pre-booked request.
- `dynamic`: Request ID → dynamic request.

## Request fields

- `id`: Zero-based request ID shared across both booking categories.
- `type`: Booking category: "prebooked" or "dynamic".
- `origin`: Origin logical stop ID.
- `destination`: Destination logical stop ID.
- `desired_time`: Desired pickup time in service-day minutes.
- `request_time`: Booking submission time in service-day minutes, possibly negative.
"""
function inst_reqs(cands, total::Int, net::NetworkData)
    allocs = scen_allocs(total)
    all_reqs = Candidate[]
    for (cell_key, n_keep) in pairs(allocs)
        append!(all_reqs, cands[string(cell_key)][1:n_keep])
    end
    sort!(all_reqs; by=item -> (
        item.request_time,  # Sort first by booking submission time.
        item.desired_time,  # Break ties by desired pickup time.
        stop_dir(net, item.origin).direction_id,  # Break remaining ties by direction.
        item.booking_type,  # Then compare booking categories.
        item.origin,  # Then compare origin logical IDs.
        item.destination,  # Then compare destination logical IDs.
        item.candidate_id,  # Use the unique candidate ID as the final tie-breaker.
    ))
    reqs = RequestGroups(
        Dict{String, Request}(),
        Dict{String, Request}(),
    )
    for (req_idx, item) in enumerate(all_reqs)
        book_type = item.booking_type
        req_id = req_idx - 1
        req = Request(
            req_id,
            book_type,
            item.origin,
            item.destination,
            item.desired_time,
            item.request_time,
        )
        req_map = book_type == "prebooked" ? reqs.prebooked : reqs.dynamic
        req_map[string(req_id)] = req
    end
    return (
        reqs,  # Scenario requests grouped by booking category.
        allocs,  # Request counts for each booking-type/direction cell.
    )
end

"""Return the earliest and latest pickup minutes around a desired service-day time."""
pickup_window(des_min) = [des_min - PICKUP_HALF_WIDTH_MIN, des_min + PICKUP_HALF_WIDTH_MIN]
