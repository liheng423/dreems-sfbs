#!/usr/bin/env julia

#=
Build a Route 550 real-time-adjusted travel-time matrix from captured ATP data.

The Python live crawler records HAFAS departure estimates that can be matched
to an active GTFS trip. This script selects the estimate closest to each
scheduled stop departure (within 15 minutes), applies the change in estimated
delay to the scheduled origin-departure-to-destination-arrival duration, and
stores the median by ordered pair. It does not substitute scheduled values for
missing real-time observations.

# Arguments

- `gtfs`: normalized GTFS crawler JSON for the captured service date.
- `obs_path`: JSON Lines output from `crawl_realtime_550.py`.
- `out_path`: destination JSON for the separate real-time matrix.
=#

using JSON3
using Statistics

include("types.jl")
include("routes.jl")
include("network.jl")
include("output.jl")

include(joinpath(@__DIR__, "..", "utilities", "utilities.jl"))

const PROJECT_ROOT = dirname(dirname(@__DIR__))
const DEFAULT_GTFS = joinpath(PROJECT_ROOT, "data", "crawled_550.json")
const DEFAULT_OUTPUT = joinpath(PROJECT_ROOT, "data", "travel_time_matrix_550.json")
const MAX_OBSERVATION_DISTANCE_SECONDS = 15 * 60

"""Read nonempty JSONL lines from obs_path into an ordered observation array."""
function read_obs(obs_path::String)
    obs_rows = Any[]
    for line in eachline(obs_path)
        isempty(line) || push!(obs_rows, JSON3.read(line))
    end
    return obs_rows
end

"""Select the closest capture within 15 minutes of each scheduled departure, preferring later captures on ties."""
function closest_obs_by_evt(obs_rows)
    closest_obs = Dict{Tuple{String, Int}, Any}()
    dist_by_evt = Dict{Tuple{String, Int}, Int}()
    for obs in obs_rows
        evt_key = (
            String(obs["trip_id"]),  # Original GTFS trip ID.
            Int(obs["stop_sequence"]),  # GTFS stop sequence number within this trip.
        )
        dist = abs(Int(obs["observed_at_service_seconds"]) - Int(obs["scheduled_departure_seconds"]))
        dist <= MAX_OBSERVATION_DISTANCE_SECONDS || continue
        if !haskey(dist_by_evt, evt_key) || dist < dist_by_evt[evt_key] ||
           (dist == dist_by_evt[evt_key] && Int(obs["observed_at_service_seconds"]) >
            Int(closest_obs[evt_key]["observed_at_service_seconds"]))
            closest_obs[evt_key] = obs
            dist_by_evt[evt_key] = dist
        end
    end
    return closest_obs
end

"""Return median travel minutes, sample counts, selected observation count, and the network."""
function build_mat(crawl, obs_rows)
    sel_obs = closest_obs_by_evt(obs_rows)
    net, timetable_pats, _ = build_net(crawl, Dict("mandatory_stop_ids" => Dict()))
    trav_samps = Dict{String, Vector{Float64}}()
    samp_counts = Dict{String, Int}()

    for (pat, net_pat) in zip(timetable_pats, net.patterns)
        logi_ids = net_pat.stops
        for trip in pat.trips
            evts = trip["stop_times"]
            trip_id = String(trip["trip_id"])
            delays = Dict{Int, Int}()
            for evt in evts
                evt_key = (
                    trip_id,  # Original GTFS trip ID.
                    Int(evt["stop_sequence"]),  # GTFS stop sequence number within this trip.
                )
                if haskey(sel_obs, evt_key)
                    obs = sel_obs[evt_key]
                    delays[Int(evt["stop_sequence"])] =
                        Int(obs["realtime_departure_seconds"]) -
                        Int(obs["scheduled_departure_seconds"])
                end
            end

            for org_idx in 1:(length(evts) - 1)
                org_evt = evts[org_idx]
                org_seq = Int(org_evt["stop_sequence"])
                haskey(delays, org_seq) || continue
                for dst_idx in (org_idx + 1):length(evts)
                    dst_evt = evts[dst_idx]
                    dst_seq = Int(dst_evt["stop_sequence"])
                    haskey(delays, dst_seq) || continue
                    trav_sec = Int(dst_evt["departure_seconds"]) -
                               Int(org_evt["departure_seconds"]) +
                               delays[dst_seq] - delays[org_seq]
                    od = od_key(logi_ids[org_idx], logi_ids[dst_idx])
                    push!(get!(trav_samps, od, Float64[]), Float64(trav_sec))
                end
            end
        end
    end

    trav_times = Dict{String, Int}()
    for (od, secs) in trav_samps
        trav_times[od] = floor(Int, median(secs) / 60)
        samp_counts[od] = length(secs)
    end
    return (
        trav_times,  # Ordered stop pair → median real-time-adjusted whole minutes.
        samp_counts,  # Ordered stop pair → number of contributing trip samples.
        length(sel_obs),  # Selected trip/stop observations, including unused ones.
        net,  # Same logical numbering and stop mapping as the scheduled network.
    )
end

"""Check observation service dates and write the real-time-adjusted matrix and metadata to out_path."""
function write_mat(crawl, obs_path::String, out_path::String)
    obs_rows = read_obs(obs_path)
    svc_date = String(first(route_crawls(crawl))["service_date"])
    all(obs -> String(obs["service_date"]) == svc_date, obs_rows) ||
        error("Observation service dates must match the GTFS service date $(svc_date)")
    all(src -> src["service_date"] == svc_date, route_crawls(crawl)) ||
        error("Route snapshots must share a service date")
    routes = [src["route"] for src in route_crawls(crawl)]
    trav_times, samp_counts, sel_count, net = build_mat(crawl, obs_rows)
    net_out = net_output(net)
    mat = (
        schema_version=2,  # Version of the matrix output format.
        routes=routes,  # Original GTFS route metadata.
        service_date=svc_date,  # Service date shared by the schedule and observations.
        network=(
            stops=[id for pat in net.patterns for id in pat.stops],
            routes=net_out.routes,
            patterns=net_out.patterns,
            source_stop_ids=net.source_stop_ids,
            travel_times=trav_times,
        ),
        sample_counts=samp_counts,  # Ordered stop pair → number of contributing trip samples.
        metadata=(  # Observation provenance and matrix construction details.
            source="ATP mobiliteit.lu HAFAS departureBoard",  # Provider and endpoint supplying the observations.
            # Clarifies that observations are estimates rather than final actual times.
            time_kind="real-time departure estimates; not final recorded actual times",
            # Description of the delay adjustment and median aggregation.
            method="scheduled origin-departure to destination-arrival duration adjusted by the difference between destination and origin HAFAS departure delays; median seconds floored to whole minutes",
            # Rule used to select one capture per trip/stop event.
            observation_selection="closest capture to each scheduled departure within 15 minutes",
            selected_stop_observations=sel_count,  # Number of selected trip/stop observations, including unused ones.
            scheduled_fallback=false,  # False because pairs without observations are omitted.
            input_observation_count=length(obs_rows),  # Number of nonempty observation records read from the input.
        ),
    )
    write_json(out_path, mat)
    println("Wrote $(length(trav_times)) observed stop-pair times to $out_path")
end

"""Build the matrix using optional GTFS, observation, and output paths from command-line args."""
function main(args=ARGS)
    gtfs = length(args) >= 1 ? abspath(args[1]) : DEFAULT_GTFS
    crawl = JSON3.read(read(gtfs, String))
    svc_date = String(first(route_crawls(crawl))["service_date"])
    obs_path = length(args) >= 2 ? abspath(args[2]) :
               joinpath(PROJECT_ROOT, "data", "realtime_550_$(svc_date).jsonl")
    out_path = length(args) >= 3 ? abspath(args[3]) : DEFAULT_OUTPUT
    write_mat(crawl, obs_path, out_path)
end

if abspath(PROGRAM_FILE) == abspath(@__FILE__)
    main()
end
