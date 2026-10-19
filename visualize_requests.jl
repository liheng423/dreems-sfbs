"""Create a PNG with saved requests and their road network."""

include(joinpath(@__DIR__, "visualizations", "requests_map.jl"))
using .RequestsMap

if isodd(length(ARGS))
    error("Usage: julia visualize_requests.jl --map MAP --instance INSTANCE [--output FILE]")
end
options = Dict{String, String}()
for i in 1:2:length(ARGS)
    ARGS[i] in ("--map", "--instance", "--output") || error("Unknown option: $(ARGS[i])")
    options[ARGS[i]] = ARGS[i + 1]
end
all(haskey(options, flag) for flag in ("--map", "--instance")) ||
    error("Usage: julia visualize_requests.jl --map MAP --instance INSTANCE [--output FILE]")
println(RequestsMap.draw_requests_map(options["--map"], options["--instance"],
                                      get(options, "--output", nothing)))
