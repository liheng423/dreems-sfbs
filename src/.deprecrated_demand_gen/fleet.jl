"""Sum each scheduled trip's consecutive road legs and apply the selected kWh/km rate."""
function trip_energy(timetable_patterns, dist_mat, fleet)
    src_idx = Dict(String(id) => idx for (idx, id) in enumerate(dist_mat["stop_ids"]))
    trips_out = NamedTuple[]
    for pattern in timetable_patterns, trip in pattern.trips
        evts = trip["stop_times"]
        dist_m = 0.0
        for idx in 1:(length(evts) - 1)
            org = String(evts[idx]["stop_id"])
            dst = String(evts[idx + 1]["stop_id"])
            leg_m = dist_mat["distances_m"][src_idx[org]][src_idx[dst]]
            leg_m === nothing && error("No road distance from $org to $dst")
            dist_m += Float64(leg_m)
        end
        push!(trips_out, (
            trip_id=String(trip["trip_id"]),
            route_id=pattern.route_id,
            pattern_id=pattern.pattern_id,
            distance_km=round(dist_m / 1000; digits=4),
            energy_kwh=round(dist_m / 1000 * fleet.energy_kwh_per_km; digits=3),
        ))
    end
    return trips_out
end
