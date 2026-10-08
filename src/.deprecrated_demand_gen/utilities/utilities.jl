"""Write a JSON value with indentation, creating its parent directory first."""
function write_json(path::AbstractString, val)
    mkpath(dirname(path))
    open(path, "w") do io
        JSON3.write(io, val; indent=2)
        write(io, '\n')
    end
end

"""Convert service-day seconds to a whole minute, rounding down."""
s2m(sec::Integer) = fld(sec, 60)

"""Build the comma-separated key used for an ordered origin/destination pair."""
od_key(org::Integer, dst::Integer) = "$(org),$(dst)"
