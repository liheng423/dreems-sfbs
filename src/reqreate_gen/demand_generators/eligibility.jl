# Enumerate timetable trip/stop pairs that can serve a request.
# Symbols follow the demand notation in src/README.md.

"""
    is_eligible_scheduled_pair(q, p, net)

Check whether a scheduled trip/stop pair allows the full pickup window within
the route pattern's service period and enough time to reach its destination.

# Arguments
- `q`: ScheduledPair with origin, destination, pickup minute, and destination departure minute.
- `p`: RoutePattern whose service period applies to the pair.
- `net`: NetworkData containing the origin-to-destination travel time.

# Returns
- `Bool`: `true` when both the service-window and travel-time conditions hold.
"""
function is_eligible_scheduled_pair(q::ScheduledPair, p::RoutePattern, net::NetworkData)
    aₚ = s2m(p.service_period.start_seconds)
    bₚ = cld(p.service_period.end_seconds, 60)
    w = PICKUP_HALF_WIDTH_MIN
    tᵢ = q.pickup_minute
    tⱼ = q.destination_departure_minute
    d = net.travel_times[od_key(q.origin, q.destination)]
    return aₚ + w <= tᵢ <= bₚ - w && tᵢ + d <= tⱼ
end

"""
    eligible_scheduled_pairs(timetable_pattern, p, net)

Enumerate feasible trip/stop pairs in timetable order. Each trip and ordered
origin/destination choice is a separate sampling opportunity.

# Arguments
- `timetable_pattern`: Timetable record with trips and their ordered stop times.
- `p`: Matching RoutePattern with logical stop IDs and service period.
- `net`: NetworkData used to check scheduled journey feasibility.

# Returns
- `Vector{ScheduledPair}` (`ℰₚ`): Eligible pairs in trip and stop order.
"""
function eligible_scheduled_pairs(timetable_pattern, p::RoutePattern, net::NetworkData)
    Sₚ = p.stops
    ℰₚ = ScheduledPair[]

    # Each eligible trip/OD combination contributes one sampling opportunity.
    # Frequencies in the timetable therefore shape the desired-time profile.
    for τ in timetable_pattern.trips
        evts = τ["stop_times"]
        for i in 1:(length(Sₚ) - 1)
            tᵢ = s2m(Int(evts[i]["departure_seconds"]))
            for j in (i + 1):length(Sₚ)
                tⱼ = s2m(Int(evts[j]["departure_seconds"]))
                q = ScheduledPair(Sₚ[i], Sₚ[j], tᵢ, tⱼ, String(τ["trip_id"]))
                is_eligible_scheduled_pair(q, p, net) && push!(ℰₚ, q)
            end
        end
    end
    return ℰₚ
end

