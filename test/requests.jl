# Run with: julia --project=. test/requests.jl
# Check the final request schema and selection against the seeded candidate pool.
include(joinpath(@__DIR__, "..", "src", "reqreate-gen", "generate.jl"))

crawl = JSON3.read(read(CRAWLED_PATH, String))
class_cfg = JSON3.read(read(CLASS_PATH, String))
net, timetable_pats, _ = build_net(crawl, class_cfg)
cands = build_cand_pool(timetable_pats, net)

# Every sampled journey obeys the timetable window and its booking lead rules.
for cell in values(cands), cand in cell
    dir = stop_pat(net, cand.origin)
    start_min = s2m(dir.service_period.start_seconds)
    end_min = cld(dir.service_period.end_seconds, 60)
    @assert start_min <= cand.desired_time - PICKUP_HALF_WIDTH_MIN
    @assert cand.desired_time + PICKUP_HALF_WIDTH_MIN <= end_min
    @assert cand.desired_time + net.travel_times[od_key(cand.origin, cand.destination)] <= cand.scheduled_arrival_minute
    lead = cand.desired_time - cand.request_time
    if cand.booking_type == "prebooked"
        @assert lead in PREBOOK_LEAD_DAYS .* 1440
    else
        @assert lead in DYN_LEAD_MIN
        @assert cand.request_time >= start_min
    end
end

for total in (0, 2, 6, last.(SCEN_REQ_COUNTS)...)
    reqs, allocs = inst_reqs(cands, total, net)
    out = JSON3.read(JSON3.write(reqs))
    req_ids = Int[]
    for book_type in ("prebooked", "dynamic")
        @assert length(out[book_type]) == total ÷ 2
        for (req_id, req) in pairs(out[book_type])
            push!(req_ids, req.id)
            @assert string(req.id) == string(req_id)
            @assert req.type == book_type
            @assert Set(keys(req)) == Set((:id, :type, :origin, :destination,
                :desired_time, :time_window, :request_time, :route_id, :pattern_id))
            @assert collect(req.time_window) == pickup_window(req.desired_time)
            @assert req.route_id == stop_pat(net, req.origin).route_id
            @assert req.pattern_id == stop_pat(net, req.origin).pattern_id
            cell_key = (book_type, String(req.route_id), String(req.pattern_id))
            alloc = only(alloc for alloc in allocs if (alloc.booking_type, alloc.route_id, alloc.pattern_id) == cell_key)
            sel = cands[cell_key][1:alloc.count]
            @assert any(cand -> (cand.origin, cand.destination, cand.desired_time, cand.request_time) ==
                (req.origin, req.destination, req.desired_time, req.request_time), sel)
        end
    end
    @assert sort(req_ids) == collect(0:(total - 1))
end
println("Request schema and seeded selection checks passed.")
