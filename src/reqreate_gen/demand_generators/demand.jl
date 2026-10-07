# Generate unlabeled passenger preferences; allocation owns booking labels and leads.
using Random

"""
Draw and filter one shared candidate pool per route pattern. Candidates contain
only OD and desired pickup time, independently of booking and bus types.
Rejected raw draws are optionally captured for debugging. Shuffling once keeps
scenario selection reproducible without changing draws when debug is enabled.
"""
function build_cand_pool(net::NetworkData; seed::Int=SEED, debug_rejected=nothing)
    rng = MersenneTwister(seed)
    cands = Dict{Tuple{String, String}, Vector{Candidate}}()
    for (p_idx, p) in enumerate(net.patterns)
        t_pickup = pickup_bounds(p, net)
        t_a = s2m(p.service_period.start_seconds)
        t_b = cld(p.service_period.end_seconds, 60)
        cell = Candidate[]
        for c_idx in 1:CAND_COUNT_PER_PATTERN
            org_idx = rand(rng, 1:length(p.stops))
            dst_idx = rand(rng, 1:(length(p.stops) - 1))
            dst_idx += dst_idx >= org_idx
            org_idx, dst_idx = minmax(org_idx, dst_idx)
            des_min = floor(Int, t_a + (t_b - t_a) * (DES_MEAN_FRACTION + DES_STD_FRACTION * randn(rng)))
            cand = Candidate("$(p_idx)_$(c_idx)", p.stops[org_idx], p.stops[dst_idx], des_min)
            if is_eligible_cand(cand, p, t_pickup)
                push!(cell, cand)
            elseif debug_rejected !== nothing
                push!(debug_rejected, cand)
            end
        end
        shuffle!(rng, cell)
        cands[(p.route_id, p.pattern_id)] = cell
    end
    return cands
end
