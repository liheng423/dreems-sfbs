# Run with: julia --project=. test/fleet.jl
# A scheduled trip visits every stop, so its road distance must include every leg.
include(joinpath(@__DIR__, "..", "src", "reqreate_gen", "generate.jl"))

crawl = JSON3.read(read(CRAWLED_PATH, String))
class_cfg = JSON3.read(read(CLASS_PATH, String))
_, timetable_patterns, _ = build_net(crawl, class_cfg)
dist_mat = JSON3.read(read(joinpath(DATA_DIR, "distance_matrix_550.json"), String))

electric = trip_energy(timetable_patterns, dist_mat, FLEET_PROFILES["electric"])
conventional = trip_energy(timetable_patterns, dist_mat, FLEET_PROFILES["conventional"])
@assert length(electric) == length(conventional) == 50
@assert length(unique(trip.trip_id for trip in electric)) == 50
@assert unique(trip.distance_km for trip in electric if trip.pattern_id == "0-00") == [29.7631]
@assert unique(trip.distance_km for trip in electric if trip.pattern_id == "1-01") == [27.402]
@assert first(electric).energy_kwh == 25.894
@assert first(conventional).energy_kwh == 132.148
println("Scheduled-trip distance and both fleet energy estimates passed.")
