# Divide each scenario total across booking types and route patterns.

"""
    scen_allocs(total, net)

Split an even total equally by booking type and as evenly as possible by pattern.
Pre-booked remainders go from the first pattern forward; dynamic remainders
start halfway through the pattern list. Prefixes remain nested as scenario totals increase.

# Arguments
- `total`: Even number of requests to allocate across both booking types.
- `net`: NetworkData whose patterns receive allocations.

# Returns
- `Vector{NamedTuple}`: One `(booking_type, route_id, pattern_id, count)` allocation per cell.
"""
function scen_allocs(total::Int, net::NetworkData)
    count = length(net.patterns)
    base, remainder = divrem(total ÷ 2, count)
    return [(
        booking_type=book_type,
        route_id=pattern.route_id,
        pattern_id=pattern.pattern_id,
        count=base + (mod(idx - 1 - offset, count) < remainder),
    ) for (book_type, offset) in (("prebooked", 0), ("dynamic", count ÷ 2))
      for (idx, pattern) in enumerate(net.patterns)]
end

