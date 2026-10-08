# Corridor timing filter adapted from Leuven's origin-based mandatory-stop check.

"""
    pickup_bounds(p, net)

Compute earliest/latest desired pickup times at each origin. A vehicle starts
at the pattern's first terminal, follows mandatory stops with their dwell,
and finishes at its last terminal with `TERM_BUFFER_MIN` to spare. Optional
origins are inserted between their neighboring mandatory stops. These bounds
are not a destination-detour or fleet-capacity feasibility proof.
"""
function pickup_bounds(p::RoutePattern, net::NetworkData)
    # retrieve data from network and pattern
    mand = filter(id -> id in net.mandatory_stops, p.stops)

    # local helper functions for travel and dwell times
    trav(org, dst) = org == dst ? 0 : net.travel_times[od_key(org, dst)]
    dwell(id) = net.dwell_times[string(id)]

    # compute arrival times at each mandatory stop, starting from the first
    arr = Dict(first(mand) => 0) # arrival time at first mandatory stop is zero
    for (org, dst) in zip(mand[1:end-1], mand[2:end]) # for each pair of consecutive mandatory stops, compute arrival time at the next
        arr[dst] = arr[org] + dwell(org) + trav(org, dst)
    end

    # compute earliest/latest pickup times at each origin
    t_a = s2m(p.service_period.start_seconds) # service start time
    t_b = cld(p.service_period.end_seconds, 60) # service end time
    # return a dictionary mapping each origin to its earliest and latest pickup times, 
    # considering the mandatory stops and travel/dwell times 
    return Dict(org => begin
        s_prev = last(id for id in mand if id <= org) # previous stops
        s_next = first(id for id in mand if id >= org) # next stops
        (max(t_a + PICKUP_HALF_WIDTH_MIN, t_a + arr[s_prev] + dwell(s_prev) + trav(s_prev, org)),
         min(t_b - PICKUP_HALF_WIDTH_MIN,
             t_b - trav(org, s_next) - (arr[last(mand)] - arr[s_next]) - TERM_BUFFER_MIN))
    end for org in p.stops)
end

"""Filter unlabeled preferences using corridor pickup bounds only."""
function is_eligible_cand(cand::Candidate, p::RoutePattern, bounds)
    early, late = bounds[cand.origin]
    return early <= cand.desired_time <= late
end
