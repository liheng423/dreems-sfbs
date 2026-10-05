#=
Core records used in network and demand calculations.

Core records store independent values; output.jl reconstructs derived JSON fields.
RequestGroups organizes selected requests before their output fields are expanded.
=#

using StructTypes

"""Mark records that serialize to JSON objects using their field names."""
abstract type JSONModel end
# Serialize each JSONModel subtype as a record of named fields.
StructTypes.StructType(::Type{<:JSONModel}) = StructTypes.Struct()

"""
Store a direction's service window measured from service-day midnight.

# Fields

- `start_seconds`: First departure in seconds from service-day midnight.
- `end_seconds`: Last arrival in seconds from service-day midnight.
"""
struct ServicePeriod <: JSONModel
    start_seconds::Int
    end_seconds::Int
end

"""
Describe one directional stop pattern and its service window.

# Fields

- `direction_id`: GTFS direction ID: "0" toward Remich or "1" toward Bettembourg for Route 550.
- `pattern_id`: GTFS pattern ID grouping trips with the same stop sequence.
- `label`: Readable direction label.
- `stops`: Logical stop IDs in travel order, numbered separately per pattern.
- `service_period`: First departure through last arrival for this pattern.
"""
struct Direction <: JSONModel
    direction_id::String
    pattern_id::String
    label::String
    stops::Vector{Int}
    service_period::ServicePeriod
end

"""
Store the corridor network with stringified logical IDs as JSON dictionary keys.

# Fields

- `directions`: Direction records with stop sequences and service windows.
- `mandatory_stops`: Logical IDs classified as mandatory by the stop configuration.
- `coordinates`: Logical ID → [longitude, latitude] in degrees.
- `stop_names`: Logical ID → original GTFS stop name.
- `source_stop_ids`: Logical ID → original GTFS stop ID.
- `travel_times`: "origin,destination" → median scheduled whole minutes for forward pairs.
- `dwell_times`: Logical ID → median scheduled dwell seconds floored to minutes.
- `class_reasons`: Logical ID → explanation of its mandatory or optional classification.
"""
struct NetworkData <: JSONModel
    directions::Vector{Direction}
    mandatory_stops::Vector{Int}
    coordinates::Dict{String, Vector{Float64}}
    stop_names::Dict{String, String}
    source_stop_ids::Dict{String, String}
    travel_times::Dict{String, Int}
    dwell_times::Dict{String, Int}
    class_reasons::Dict{String, String}
end

"""
Store one feasible scheduled trip and ordered origin/destination combination.

# Fields

- `org`: Origin logical stop ID.
- `dst`: Destination logical stop ID after the origin.
- `des_min`: Scheduled pickup time in whole service-day minutes.
- `sched_arr_min`: Scheduled destination arrival in whole service-day minutes.
- `src_trip_id`: Original GTFS trip ID supplying this pair.
"""
struct SchedPair
    org::Int
    dst::Int
    des_min::Int
    sched_arr_min::Int
    src_trip_id::String
end

"""
Store a sampled request with logical stop IDs and its source trip.

# Fields

- `candidate_id`: Unique booking-type_direction_index identifier within the candidate pool.
- `origin`: Origin logical stop ID.
- `destination`: Destination logical stop ID.
- `booking_type`: Booking category: "prebooked" or "dynamic".
- `desired_time`: Desired pickup time in service-day minutes.
- `request_time`: Booking submission time in service-day minutes, possibly negative.
- `source_trip_id`: Original GTFS trip ID used to generate the candidate.
- `scheduled_arrival_minute`: Source trip's destination arrival in whole service-day minutes.
"""
struct Candidate <: JSONModel
    candidate_id::String
    origin::Int
    destination::Int
    booking_type::String
    desired_time::Int
    request_time::Int
    source_trip_id::String
    scheduled_arrival_minute::Int
end

"""
Store a selected scenario request before deriving its output direction and pickup window.

# Fields

- `id`: Zero-based request ID shared across both booking categories.
- `type`: Booking category: "prebooked" or "dynamic".
- `origin`: Origin logical stop ID.
- `destination`: Destination logical stop ID.
- `desired_time`: Desired pickup time in service-day minutes.
- `request_time`: Booking submission time in service-day minutes, possibly negative.
"""
struct Request <: JSONModel
    id::Int
    type::String
    origin::Int
    destination::Int
    desired_time::Int
    request_time::Int
end

"""
Group scenario requests by booking category using stringified request IDs.

# Fields

- `prebooked`: Request ID → pre-booked request.
- `dynamic`: Request ID → dynamic request.
"""
struct RequestGroups <: JSONModel
    prebooked::Dict{String, Request}
    dynamic::Dict{String, Request}
end
