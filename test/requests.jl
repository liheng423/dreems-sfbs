# Run with: julia --project=. test/requests.jl
include(joinpath(@__DIR__, "..", "src", "reqreate_gen", "generate.jl"))
crawl = JSON3.read(read(CRAWLED_PATH, String))
class_cfg = JSON3.read(read(CLASS_PATH, String))
net, _, _ = build_net(crawl, class_cfg)
debug_rejected = Candidate[]
cands = build_cand_pool(net; debug_rejected)
@assert JSON3.write(cands) == JSON3.write(build_cand_pool(net))
@assert sum(length, values(cands)) + length(debug_rejected) == length(net.patterns) * CAND_COUNT_PER_PATTERN
@assert !hasfield(Candidate, :booking_type) && !hasfield(Candidate, :request_time)
for cell in values(cands), cand in cell
    p = stop_pattern(net, cand.origin)
    @assert is_eligible_cand(cand, p, pickup_bounds(p, net))
end
for cand in debug_rejected
    @assert !isempty(rejected_cand_output(cand, net).rejection_reasons)
end

# Exact complementary proportions, unique shared candidates, valid leads and schema.
for total in (0, 1, 7, 50), prebook_share in (0.0, 0.3, 0.5, 1.0), electric_share in (0.0, 0.4, 1.0)
    sel, allocs = select_instance_candidates(cands, total, net; prebook_share)
    reqs = requests_output(sel, net; electric_share)
    @assert length(Set(c.candidate_id for c in sel)) == total
    @assert length(reqs.prebooked) == floor(Int, total * prebook_share + 0.5)
    @assert length(reqs.dynamic) == total - length(reqs.prebooked)
    all_reqs = collect(Iterators.flatten((values(reqs.prebooked), values(reqs.dynamic))))
    @assert count(req -> req.bus_type == "electric", all_reqs) == floor(Int, total * electric_share + 0.5)
    @assert sum(a.count for a in allocs) == total
    @assert sort([req.id for req in all_reqs]) == collect(0:total-1)
    for cand in sel
        p = stop_pattern(net, cand.origin)
        @assert any(raw -> raw.candidate_id == cand.candidate_id && raw.origin == cand.origin &&
            raw.destination == cand.destination && raw.desired_time == cand.desired_time,
            cands[(p.route_id, p.pattern_id)])
        lead = cand.desired_time - cand.request_time
        if cand.booking_type == "prebooked"
            @assert lead in PREBOOK_LEAD_DAYS .* 1440
        else
            @assert lead in DYN_LEAD_MIN
            @assert cand.request_time >= s2m(p.service_period.start_seconds)
        end
    end
    for req in all_reqs
        @assert Set(keys(req)) == Set((:id, :type, :origin, :destination, :desired_time,
            :time_window, :request_time, :route_id, :pattern_id, :bus_type))
        @assert req.time_window == pickup_window(req.desired_time)
    end
end
small, _ = select_instance_candidates(cands, 50, net)
large, _ = select_instance_candidates(cands, 100, net)
@assert issubset(Set(small), Set(large)) # Includes booking labels and request timestamps.

# Known pickup bounds and a dynamic draw that cannot fit even the minimum lead.
p = RoutePattern("T_0", "p", [1, 2, 3], ServicePeriod(360*60, 540*60), "T", "0", "test")
fixture = NetworkData([p], Dict("1,2"=>7, "1,3"=>20, "2,3"=>8), [1,3],
    Dict{String,Vector{Float64}}(), Dict{String,String}(),
    Dict(string(id)=>"stop_$id" for id in 1:3), Dict("1"=>2,"2"=>0,"3"=>2), Dict{String,String}())
bounds = pickup_bounds(p, fixture)
@assert bounds[2] == (369,527)
@assert is_eligible_cand(Candidate("a",2,3,369), p, bounds)
@assert !is_eligible_cand(Candidate("a",2,3,368), p, bounds)
raw = [Candidate("early",1,3,364), Candidate("later",2,3,420)]
pool = Dict((p.route_id,p.pattern_id)=>raw)
rejected = NamedTuple[]
sel, _ = select_instance_candidates(pool, 1, fixture; prebook_share=0.0, debug_rejected=rejected)
@assert only(sel).candidate_id == "later"
@assert only(rejected).candidate.candidate_id == "early"
@assert only(rejected).request_time < 360
@assert sel == first(select_instance_candidates(pool, 1, fixture; prebook_share=0.0))
pre, _ = select_instance_candidates(pool, 1, fixture; prebook_share=1.0)
@assert only(pre).candidate_id == "early" # Same raw pool, label changes lead rules.
try
    select_instance_candidates(pool, 3, fixture)
    error("Expected exhausted pool to fail")
catch err
    @assert occursin("Candidate pool exhausted", sprint(showerror, err))
end
println("Shared pool, label allocation, leads, debug rejection, nesting, and exhaustion passed.")
