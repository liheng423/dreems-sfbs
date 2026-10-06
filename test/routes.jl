# Run with: julia --project=. test/routes.jl
# Same-feed routes reuse direction/pattern IDs and share physical stops.
include(joinpath(@__DIR__, "..", "src", "reqreate-gen", "generate.jl"))

function fixture_pat(pat_id, dir_id, src_ids)
    trips = [Dict(
        "trip_id" => "$(pat_id)_$(start_sec)",
        "stop_times" => [Dict("stop_id" => id, "stop_sequence" => idx,
            "departure_seconds" => start_sec + 600 * (idx - 1))
            for (idx, id) in enumerate(src_ids)],
    ) for start_sec in (3600, 7200)]
    Dict("pattern_id" => pat_id, "direction_id" => dir_id, "label" => pat_id,
        "stop_ids" => src_ids, "trips" => trips,
        "service_period" => Dict("first_departure_seconds" => 3600,
            "last_arrival_seconds" => 7200 + 600 * (length(src_ids) - 1)))
end

function fixture_crawl(route_id, pats)
    for pat in pats, trip in pat["trips"]
        trip["trip_id"] = "$(route_id)_$(trip["trip_id"])"
    end
    src_ids = unique([id for pat in pats for id in pat["stop_ids"]])
    Dict("route" => Dict("route_id" => route_id), "patterns" => pats,
        "stops" => [Dict("stop_id" => id, "stop_name" => id,
            "stop_lon" => 6.0, "stop_lat" => 49.0) for id in src_ids])
end

crawls = [
    fixture_crawl("A", [fixture_pat("full", "0", ["X", "Y", "X"]),
        fixture_pat("short", "0", ["X", "Y"]),
        fixture_pat("return", "1", ["Y", "X"])]),
    fixture_crawl("B", [fixture_pat("full", "0", ["X", "Z"])]),
]
net, timetable_pats, _ = build_net(crawls, Dict("mandatory_stop_ids" => Dict()))
@assert length(net.patterns) == 4
@assert all(first(pat.stops) in net.mandatory_stops && last(pat.stops) in net.mandatory_stops for pat in net.patterns)
@assert Set(pat.route_id for pat in net.patterns) == Set(["A_0", "A_1", "B_0"])
@assert length(logi_stop_ids(net, "X")) == 5 # Includes both visits on the loop.
@assert length(unique(id for pat in net.patterns for id in pat.stops)) == 9
@assert all(id -> src_stop_id(net, id) == "X", logi_stop_ids(net, "X"))
out = JSON3.read(JSON3.write(net_output(net)))
@assert length(out.routes) == 3
@assert Set(first(out.routes).pattern_ids) == Set(["full", "short"])

cands = build_cand_pool(timetable_pats, net)
@assert length(cands) == 8
for ((book_type, route_id, pat_id), cell) in cands, cand in cell
    pat = stop_pat(net, cand.origin)
    @assert (pat.route_id, pat.pattern_id) == (route_id, pat_id)
    @assert stop_pat(net, cand.destination) === pat
    @assert cand.booking_type == book_type
end
for total in 0:2:40
    reqs, allocs = inst_reqs(cands, total, net)
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
include(joinpath(@__DIR__, "..", "src", "reqreate-gen", "travel_time_matrix.jl"))
end
obs = [Dict(
    "trip_id" => first(pat["trips"])["trip_id"],
    "stop_sequence" => evt["stop_sequence"],
    "observed_at_service_seconds" => evt["departure_seconds"],
    "scheduled_departure_seconds" => evt["departure_seconds"],
    "realtime_departure_seconds" => evt["departure_seconds"] + 60 * evt["stop_sequence"],
) for src in crawls for pat in src["patterns"] for evt in first(pat["trips"])["stop_times"]]
trav_times, samp_counts, sel_count, rt_net = Realtime.build_mat(crawls, obs)
@assert rt_net.source_stop_ids == net.source_stop_ids
@assert sel_count == 9
for pat in net.patterns, org_idx in 1:(length(pat.stops) - 1), dst_idx in (org_idx + 1):length(pat.stops)
    key = od_key(pat.stops[org_idx], pat.stops[dst_idx])
    @assert trav_times[key] == 11 * (dst_idx - org_idx)
    @assert samp_counts[key] == 1
end
println("Real-time route numbering and delay-adjusted travel times passed.")
