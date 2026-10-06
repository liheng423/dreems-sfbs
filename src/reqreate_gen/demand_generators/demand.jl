# Sample candidates and select them for demand scenarios.
# Included after eligibility.jl and allocations.jl by generate.jl.
# Symbols follow the demand notation in src/README.md.

using Random

"""
    build_cand_pool(timetable_patterns, net; seed=SEED)

Sample and shuffle candidates independently for each booking type and route
pattern. Dynamic pairs must permit at least the minimum booking lead after
service starts; each cell contains `CAND_COUNT_PER_CELL` candidates.

# Arguments
- `timetable_patterns`: Timetable records matched to network patterns by route and pattern ID.
- `net`: NetworkData supplying patterns, service periods, and travel times.
- `seed`: Random seed for reproducible pair, lead-time, and shuffle draws.

# Returns
- `Dict` (`candidate_pool`): Maps `(booking_type, route_id, pattern_id)` to a shuffled `Vector{Candidate}`.
"""
function build_cand_pool(timetable_patterns, net; seed::Int=SEED)
    rng = MersenneTwister(seed)
    candidate_pool = Dict()
    patterns = Dict((pattern.route_id, pattern.pattern_id) => pattern for pattern in timetable_patterns)
    for (p_idx, p) in enumerate(net.patterns)
        timetable_pattern = patterns[(p.route_id, p.pattern_id)]
        ℰₚ = eligible_scheduled_pairs(timetable_pattern, p, net)
        aₚ = s2m(p.service_period.start_seconds)
        # Dynamic bookings need room for their minimum lead after service starts.
        ℰ_dynamic = filter(q -> q.pickup_minute - aₚ >= first(DYN_LEAD_MIN), ℰₚ)
        # Preserve cell order and draw pair → lead → shuffle for seeded reproducibility.
        for (b, ℰᵦₚ) in (("prebooked", ℰₚ), ("dynamic", ℰ_dynamic))
            Cᵦₚ = Candidate[]
            for c_idx in 1:CAND_COUNT_PER_CELL
                q::ScheduledPair = rand(rng, ℰᵦₚ)
                lead_min = if b == "prebooked"
                    rand(rng, PREBOOK_LEAD_DAYS) * 1440
                else
                    max_lead_min = min(last(DYN_LEAD_MIN), q.pickup_minute - aₚ)
                    rand(rng, first(DYN_LEAD_MIN):max_lead_min)
                end
                push!(Cᵦₚ, Candidate("$(b)_$(p_idx)_$(c_idx)", q, b, lead_min))
            end
            shuffle!(rng, Cᵦₚ)
            candidate_pool[(b, p.route_id, p.pattern_id)] = Cᵦₚ
        end
    end
    return candidate_pool
end

"""
    select_instance_candidates(cands, total, net)

Select each cell's allocated prefix from the candidate pool, sort the selected
candidates by booking time with deterministic tie breakers.

# Arguments
- `cands`: Candidate pool keyed by `(booking_type, route_id, pattern_id)`.
- `total`: Even number of requests for this scenario.
- `net`: NetworkData used for allocations and each request's route and pattern IDs.

# Returns
- `sel`: Selected candidates in the order used for scenario request IDs.
- `allocs`: Per-cell allocation records returned by `scen_allocs(total, net)`.
"""
function select_instance_candidates(cands, total::Int, net::NetworkData)
    allocs = scen_allocs(total, net)
    sel = Candidate[cand for alloc in allocs
                    for cand in cands[(alloc.booking_type, alloc.route_id, alloc.pattern_id)][1:alloc.count]]
    # Booking time comes first; the remaining fields deterministically break ties.
    sort!(sel; by=cand -> (
        cand.request_time, cand.desired_time, stop_pattern(net, cand.origin).route_id,
        cand.booking_type, cand.origin, cand.destination, cand.candidate_id,
    ))
    return sel, allocs
end
