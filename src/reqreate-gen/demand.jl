#=
Generate demand in three steps:
1. Enumerate feasible scheduled trip/OD pairs in timetable order.
2. Sample booking leads and shuffle a candidate pool for each booking/route/pattern cell.
3. Take cell prefixes, sort by booking time, and number the scenario requests.

Larger scenarios reuse the same prefixes, so their candidate samples are nested.

Included by `generate.jl`; settings are defined in `demand_config.jl`.
=#

using Random

"""Check whether a scheduled trip/OD pair fits the pattern's service hours and travel time."""
function is_eligible_scheduled_pair(pair::SchedPair, net_pat::RoutePattern, net::NetworkData)
    start_min = s2m(net_pat.service_period.start_seconds)
    end_min = cld(net_pat.service_period.end_seconds, 60)
    return start_min + PICKUP_HALF_WIDTH_MIN <= pair.des_min <= end_min - PICKUP_HALF_WIDTH_MIN &&
           pair.des_min + net.travel_times[od_key(pair.org, pair.dst)] <= pair.sched_arr_min
end

"""
List trip/stop pairs whose pickup windows and scheduled journeys fit the pattern timetable.
"""
function eligible_scheduled_pairs(pat, net_pat::RoutePattern, net::NetworkData)
    logi_stops = net_pat.stops
    scheduled_pairs = SchedPair[]

    # Each eligible trip/OD combination contributes one sampling opportunity.
    # Frequencies in the timetable therefore shape the desired-time profile.
    for trip in pat.trips
        evts = trip["stop_times"]
        for org_idx in 1:(length(logi_stops) - 1)
            org = logi_stops[org_idx]
            des_min = s2m(Int(evts[org_idx]["departure_seconds"]))
            for dst_idx in (org_idx + 1):length(logi_stops)
                dst = logi_stops[dst_idx]
                arr_min = s2m(Int(evts[dst_idx]["departure_seconds"]))
                pair = SchedPair(org, dst, des_min, arr_min, String(trip["trip_id"]))
                is_eligible_scheduled_pair(pair, net_pat, net) && push!(scheduled_pairs, pair)
            end
        end
    end
    return scheduled_pairs
end

"""
Sample and shuffle seeded candidate requests for each booking type and route pattern.
"""
function build_cand_pool(timetable_pats, net; seed::Int=SEED)
    rng = MersenneTwister(seed)
    cands = Dict()
    pats = Dict((pat.route_id, pat.pattern_id) => pat for pat in timetable_pats)
    for (pat_idx, net_pat) in enumerate(net.patterns)
        pat = pats[(net_pat.route_id, net_pat.pattern_id)]
        scheduled_pairs = eligible_scheduled_pairs(pat, net_pat, net)
        start_min = s2m(net_pat.service_period.start_seconds)
        # Dynamic bookings need room for their minimum lead after service starts.
        dyn_pairs = filter(pair -> pair.des_min - start_min >= first(DYN_LEAD_MIN), scheduled_pairs)
        # Preserve cell order and draw pair → lead → shuffle for seeded reproducibility.
        for (book_type, eligible_pairs) in (("prebooked", scheduled_pairs), ("dynamic", dyn_pairs))
            cand_cell = Candidate[]
            for cand_idx in 1:CAND_COUNT_PER_CELL
                pair = rand(rng, eligible_pairs)
                lead = if book_type == "prebooked"
                    rand(rng, PREBOOK_LEAD_DAYS) * 1440
                else
                    max_lead = min(last(DYN_LEAD_MIN), pair.des_min - start_min)
                    rand(rng, first(DYN_LEAD_MIN):max_lead)
                end
                push!(cand_cell, Candidate(
                    "$(book_type)_$(pat_idx)_$(cand_idx)",
                    pair.org,
                    pair.dst,
                    book_type,
                    pair.des_min,
                    pair.des_min - lead,
                    pair.src_trip_id,
                    pair.sched_arr_min,
                ))
            end
            shuffle!(rng, cand_cell)
            cands[(book_type, net_pat.route_id, net_pat.pattern_id)] = cand_cell
        end
    end
    return cands
end

"""
Split an even total equally by booking type and as evenly as possible by pattern.
Pre-booked remainders go from the first pattern forward; dynamic remainders
start halfway through the pattern list. Prefixes remain nested as scenario totals increase.
"""
function scen_allocs(total::Int, net::NetworkData)
    count = length(net.patterns)
    base, remainder = divrem(total ÷ 2, count)
    return [(
        booking_type=book_type,
        route_id=pat.route_id,
        pattern_id=pat.pattern_id,
        count=base + (mod(idx - 1 - offset, count) < remainder),
    ) for (book_type, offset) in (("prebooked", 0), ("dynamic", count ÷ 2))
      for (idx, pat) in enumerate(net.patterns)]
end

"""
Return numbered scenario requests and cell allocations from prefixes of the candidate pool.
"""
function inst_reqs(cands, total::Int, net::NetworkData)
    allocs = scen_allocs(total, net)
    sel = Candidate[cand for alloc in allocs
                    for cand in cands[(alloc.booking_type, alloc.route_id, alloc.pattern_id)][1:alloc.count]]
    # Booking time comes first; the remaining fields deterministically break ties.
    sort!(sel; by=cand -> (
        cand.request_time, cand.desired_time, stop_pat(net, cand.origin).route_id,
        cand.booking_type, cand.origin, cand.destination, cand.candidate_id,
    ))
    reqs = (prebooked=Dict{String, NamedTuple}(), dynamic=Dict{String, NamedTuple}())
    for (req_idx, cand) in enumerate(sel)
        book_type = cand.booking_type
        req_id = req_idx - 1
        # Emit the scenario schema directly; IDs span both booking categories.
        req = (
            id=req_id,
            type=book_type,
            origin=cand.origin,
            destination=cand.destination,
            desired_time=cand.desired_time,
            time_window=pickup_window(cand.desired_time),
            request_time=cand.request_time,
            route_id=stop_pat(net, cand.origin).route_id,
            pattern_id=stop_pat(net, cand.origin).pattern_id,
        )
        req_map = book_type == "prebooked" ? reqs.prebooked : reqs.dynamic
        req_map[string(req_id)] = req
    end
    return reqs, allocs
end

"""Return the earliest and latest pickup minutes around a desired service-day time."""
pickup_window(des_min) = [des_min - PICKUP_HALF_WIDTH_MIN, des_min + PICKUP_HALF_WIDTH_MIN]
