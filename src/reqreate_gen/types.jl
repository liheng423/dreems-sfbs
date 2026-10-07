#=
Core records used in network and demand calculations.

Core records store independent values; output.jl reconstructs derived JSON fields.
=#

"""
Store a pattern's service window measured from service-day midnight.

# Fields

- `start_seconds`: First departure in seconds from service-day midnight.
- `end_seconds`: Last arrival in seconds from service-day midnight.
"""
struct ServicePeriod
    start_seconds::Int
    end_seconds::Int
end

"""
Describe one directional stop pattern and its service window.

# Fields

- `route_id`: Internal directed route ID, combining source route and direction.
- `pattern_id`: GTFS pattern ID grouping trips with the same stop sequence.
- `stops`: Logical stop IDs in travel order, numbered separately per pattern.
- `service_period`: First departure through last arrival for this pattern.
- `source_route_id`: Original GTFS route ID.
- `source_direction_id`: Original GTFS direction ID.
- `label`: Readable direction label.
"""
struct RoutePattern
    # Demand-generation fields.
    route_id::String
    pattern_id::String
    stops::Vector{Int}
    service_period::ServicePeriod

    # Source and output fields; not used to make demand decisions.
    source_route_id::String
    source_direction_id::String
    label::String
end

"""
Store the corridor network with stringified logical IDs as JSON dictionary keys.

# Fields

- `patterns`: Directed route patterns with logical stop sequences and service windows.
- `travel_times`: "origin,destination" → median scheduled whole minutes for forward pairs.
- `mandatory_stops`: Logical IDs classified as mandatory by the stop configuration.
- `coordinates`: Logical ID → [longitude, latitude] in degrees.
- `stop_names`: Logical ID → original GTFS stop name.
- `source_stop_ids`: Logical ID → original GTFS stop ID.
- `dwell_times`: Logical ID → configured service dwell in whole minutes.
- `class_reasons`: Logical ID → explanation of its mandatory or optional classification.
"""
struct NetworkData
    # Demand-generation fields.
    patterns::Vector{RoutePattern}
    travel_times::Dict{String, Int}

    # Mandatory stops and dwell times also determine demand feasibility.
    mandatory_stops::Vector{Int}
    coordinates::Dict{String, Vector{Float64}}
    stop_names::Dict{String, String}
    source_stop_ids::Dict{String, String}
    dwell_times::Dict{String, Int}
    class_reasons::Dict{String, String}
end

"""
Store a synthetic passenger preference independent of scheduled departures.

`candidate_id` identifies the raw draw, including gaps left by rejected draws.
Desired pickup time is in whole service-day minutes. Booking type and
request timestamp are assigned later by allocation.
"""
struct Candidate
    candidate_id::String
    origin::Int
    destination::Int
    desired_time::Int
end
