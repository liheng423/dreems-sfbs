# Run with: julia --project=. test/routes.jl
# Same-feed routes reuse direction/pattern IDs and share physical stops.
include(joinpath(@__DIR__, "..", "src", "reqreate_gen", "generate.jl"))

function fixture_pattern(pattern_id, dir_id, src_ids)
    trips = [Dict(
        "trip_id" => "$(pattern_id)_$(start_sec)",
        "stop_times" => [Dict("stop_id" => id, "stop_sequence" => idx,
            "departure_seconds" => start_sec + 600 * (idx - 1))
            for (idx, id) in enumerate(src_ids)],
    ) for start_sec in (3600, 7200)]
    Dict("pattern_id" => pattern_id, "direction_id" => dir_id, "label" => pattern_id,
        "stop_ids" => src_ids, "trips" => trips,
        "service_period" => Dict("first_departure_seconds" => 3600,
            "last_arrival_seconds" => 7200 + 600 * (length(src_ids) - 1)))
end

function fixture_crawl(route_id, patterns)
    for pattern in patterns, trip in pattern["trips"]
        trip["trip_id"] = "$(route_id)_$(trip["trip_id"])"
    end
    src_ids = unique([id for pattern in patterns for id in pattern["stop_ids"]])
    Dict("route" => Dict("route_id" => route_id), "patterns" => patterns,
        "stops" => [Dict("stop_id" => id, "stop_name" => id,
            "stop_lon" => 6.0, "stop_lat" => 49.0) for id in src_ids])
end

crawls = [
    fixture_crawl("A", [fixture_pattern("full", "0", ["X", "Y", "X"]),
        fixture_pattern("short", "0", ["X", "Y"]),
        fixture_pattern("return", "1", ["Y", "X"])]),
    fixture_crawl("B", [fixture_pattern("full", "0", ["X", "Z"])]),
]
net, timetable_patterns, _ = build_net(crawls, Dict("mandatory_stop_ids" => Dict()))
@assert length(net.patterns) == 4
@assert all(first(pattern.stops) in net.mandatory_stops && last(pattern.stops) in net.mandatory_stops for pattern in net.patterns)
@assert Set(pattern.route_id for pattern in net.patterns) == Set(["A_0", "A_1", "B_0"])
@assert length(logi_stop_ids(net, "X")) == 5 # Includes both visits on the loop.
@assert length(unique(id for pattern in net.patterns for id in pattern.stops)) == 9
@assert all(id -> src_stop_id(net, id) == "X", logi_stop_ids(net, "X"))
out = JSON3.read(JSON3.write(net_output(net)))
@assert length(out.routes) == 3
@assert Set(first(out.routes).pattern_ids) == Set(["full", "short"])

cands = build_cand_pool(timetable_patterns, net)
@assert length(cands) == 8
for ((book_type, route_id, pattern_id), cell) in cands, cand in cell
    pattern = stop_pattern(net, cand.origin)
    @assert (pattern.route_id, pattern.pattern_id) == (route_id, pattern_id)
    @assert stop_pattern(net, cand.destination) === pattern
    @assert cand.booking_type == book_type
end
for total in 0:2:40
    sel, allocs = select_instance_candidates(cands, total, net)
    reqs = requests_output(sel, net)
    @assert length(reqs.prebooked) == length(reqs.dynamic) == total ÷ 2
    @assert sum(alloc.count for alloc in allocs) == total
    next_allocs = scen_allocs(total + 2, net)
    @assert all(a.count <= b.count for (a, b) in zip(allocs, next_allocs))
    for alloc in allocs
        req_map = alloc.booking_type == "prebooked" ? reqs.prebooked : reqs.dynamic
        @assert count(req -> (req.route_id, req.pattern_id) == (alloc.route_id, alloc.pattern_id),
            values(req_map)) == alloc.count
    end
end
println("Directed routes, branches, shared stops, loop visits, and allocations passed.")

# Real-time matrices must use exactly the scheduled network's logical numbering.
module Realtime
include(joinpath(@__DIR__, "..", "src", "reqreate_gen", "travel_time_matrix.jl"))
end
obs = [Dict(
    "trip_id" => first(pattern["trips"])["trip_id"],
    "stop_sequence" => evt["stop_sequence"],
    "observed_at_service_seconds" => evt["departure_seconds"],
    "scheduled_departure_seconds" => evt["departure_seconds"],
    "realtime_departure_seconds" => evt["departure_seconds"] + 60 * evt["stop_sequence"],
) for src in crawls for pattern in src["patterns"] for evt in first(pattern["trips"])["stop_times"]]
trav_times, samp_counts, sel_count, rt_net = Realtime.build_mat(crawls, obs)
@assert rt_net.source_stop_ids == net.source_stop_ids
@assert sel_count == 9
for pattern in net.patterns, org_idx in 1:(length(pattern.stops) - 1), dst_idx in (org_idx + 1):length(pattern.stops)
    key = od_key(pattern.stops[org_idx], pattern.stops[dst_idx])
    @assert trav_times[key] == 11 * (dst_idx - org_idx)
    @assert samp_counts[key] == 1
end
println("Real-time route numbering and delay-adjusted travel times passed.")
