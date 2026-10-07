# Divide each scenario total across booking types and route patterns.


"""
Allocate electric/conventional service to requests in their output order.
Cumulative nearest-integer rounding spreads electric labels through the list
and gives round-half-up(total * electric_share) electric requests overall.
This is a scenario service-type assignment, not a vehicle dispatch decision.
Labels are recomputed per scenario; nested candidates need not keep their label.
"""
function bus_allocs(sel; electric_share=ELECTRIC_SHARE)
    return [floor(Int, idx * electric_share + 0.5) > floor(Int, (idx - 1) * electric_share + 0.5) ?
            "electric" : "conventional" for idx in eachindex(sel)]
end

"""
Select from shared pattern pools, then assign booking labels and sample leads.
Cumulative rounding gives the configured pre-booked count (nearest, ties up).
Each booking category cycles through patterns; dynamic starts halfway through.
A dynamic assignment revealed before service starts is rejected and replaced
from the same pool, without relabeling it or shortening its sampled lead.

Restarting the seeded allocation for a larger total preserves the accepted
candidate/booking/timestamp prefix. Each raw candidate is consumed at most once
per scenario. Optional debug records capture failed dynamic assignments.
"""
function select_instance_candidates(cands, total::Int, net::NetworkData;
        prebook_share=PREBOOK_SHARE, seed::Int=SEED, debug_rejected=nothing)
    rng = MersenneTwister(seed)
    cursors = zeros(Int, length(net.patterns))
    book_counts = Dict("prebooked" => 0, "dynamic" => 0)
    sel = NamedTuple[]
    for req_idx in 1:total
        is_prebook = floor(Int, req_idx * prebook_share + 0.5) > floor(Int, (req_idx - 1) * prebook_share + 0.5)
        book_type = is_prebook ? "prebooked" : "dynamic"
        offset = is_prebook ? 0 : length(net.patterns) ÷ 2
        p_idx = mod(book_counts[book_type] + offset, length(net.patterns)) + 1
        p = net.patterns[p_idx]
        cell = cands[(p.route_id, p.pattern_id)]
        while true
            cursors[p_idx] += 1
            cursors[p_idx] <= length(cell) || error("Candidate pool exhausted for $(p.route_id)/$(p.pattern_id) while allocating $book_type requests")
            cand = cell[cursors[p_idx]]
            lead_min = is_prebook ? rand(rng, PREBOOK_LEAD_DAYS) * 1440 : rand(rng, DYN_LEAD_MIN)
            req_time = cand.desired_time - lead_min
            if !is_prebook && req_time < s2m(p.service_period.start_seconds)
                debug_rejected !== nothing && push!(debug_rejected,
                    (candidate=cand, booking_type=book_type, request_time=req_time))
                continue
            end
            push!(sel, (candidate_id=cand.candidate_id, origin=cand.origin,
                destination=cand.destination, desired_time=cand.desired_time,
                booking_type=book_type, request_time=req_time))
            book_counts[book_type] += 1
            break
        end
    end
    sort!(sel; by=cand -> (cand.request_time, cand.desired_time,
        stop_pattern(net, cand.origin).route_id, cand.booking_type,
        cand.origin, cand.destination, cand.candidate_id))
    allocs = [(booking_type=book_type, route_id=p.route_id, pattern_id=p.pattern_id,
        count=count(cand -> cand.booking_type == book_type && cand.origin in p.stops, sel))
        for book_type in ("prebooked", "dynamic") for p in net.patterns]
    return sel, allocs
end
