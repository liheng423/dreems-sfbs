module RequestsMap

using JSON3, Luxor

const ROOT = normpath(joinpath(@__DIR__, ".."))

function draw_requests_map(graph_name::AbstractString, instance::AbstractString,
                           output_file::Union{Nothing, AbstractString}=nothing)
    for name in (graph_name, instance)
        (isempty(name) || name in (".", "..") || basename(name) != name) &&
            error("Map and instance must be folder names")
    end
    requests_file = joinpath(ROOT, "outputs", "requests", instance, "requests.json")
    requests = collect(values(JSON3.read(read(requests_file, String)).requests))
    settings = Dict{String, String}()
    for line in Iterators.take(eachline(joinpath(dirname(requests_file), "parameters.txt")), 3)
        key, value = split(line, " = "; limit=2)
        settings[key] = value
    end
    busline = JSON3.read(settings["task"]) == "SFBS" ? String(JSON3.read(settings["busline"])) : nothing
    route_lines = Vector{Tuple{Float64, Float64}}[]
    route_stops = Tuple{Float64, Float64}[]
    if !isnothing(busline)
        occursin(r"^[A-Za-z0-9-]+$", busline) || error("Invalid busline name")
        info = JSON3.read(read(joinpath(ROOT, "outputs", "buslines", busline, "buslines.json"), String))
        stops = Dict(String(stop.stop_id) => (Float64(stop.stop_lon), Float64(stop.stop_lat))
                     for stop in info.stops)
        stops_path = joinpath(ROOT, "outputs", "buslines", busline, "stops.json")
        if isfile(stops_path)
            for stop in JSON3.read(read(stops_path, String))
                stops[replace(String(stop.name), r"^Stop_" => "")] = (Float64(stop.lon), Float64(stop.lat))
            end
        end
        route_stops = collect(values(stops))
        route_lines = [[stops[String(id)] for id in (hasproperty(pattern, :selected_stop_ids) ? pattern.selected_stop_ids : pattern.stop_ids)] for pattern in info.patterns]
    end
    graph_dir = joinpath(ROOT, "outputs", "graphs", graph_name)
    output_file = isnothing(output_file) ? joinpath(ROOT, "visualizations", "$(basename(dirname(requests_file)))_requests_map.png") : abspath(output_file)

    nodes = Dict{String, Tuple{Float64, Float64}}()
    for row in Iterators.drop(eachline(joinpath(graph_dir, "drive_nodes.csv")), 1)
        fields = split(row, ','; limit=4)
        nodes[String(fields[1])] = (parse(Float64, fields[2]), parse(Float64, fields[3]))
    end
    roads = Vector{Tuple{Float64, Float64}}[]
    for row in Iterators.drop(eachline(joinpath(graph_dir, "drive_edges.csv")), 1)
        fields = split(row, ','; limit=5)
        geometry = match(r"^\"(LINESTRING \([^\"]+\))\"", fields[5])
        if isnothing(geometry)
            push!(roads, [nodes[String(fields[1])], nodes[String(fields[2])]])
        else
            coords = replace(geometry.captures[1], r"^LINESTRING \(|\)$" => "")
            push!(roads, [Tuple(parse.(Float64, split(strip(point)))) for point in split(coords, ',')])
        end
    end
    pois = JSON3.read(read(joinpath(graph_dir, "pois.json"), String)).features
    parking = Tuple{Float64, Float64}[]
    charging = Tuple{Float64, Float64}[]
    locations_path = joinpath(graph_dir, "locations.csv")
    if isfile(locations_path)
        for row in Iterators.drop(eachline(locations_path), 1)
            fields = split(row, ',')
            point = (parse(Float64, fields[3]), parse(Float64, fields[4]))
            fields[1] == "parking" && push!(parking, point)
            fields[1] == "charging" && push!(charging, point)
        end
    end
    depot = JSON3.read(read(joinpath(graph_dir, "depot.json"), String))
    area = JSON3.read(read(joinpath(graph_dir, "service_area.geojson"), String)).geometry
    polygons = area.type == "Polygon" ? (area.coordinates,) : area.coordinates
    boundaries = [[(Float64(point[1]), Float64(point[2])) for point in ring]
                  for polygon in polygons for ring in polygon]
    depot_point = (Float64(depot.drive_point[2]), Float64(depot.drive_point[1]))
    origins = [(Float64(req.origin[2]), Float64(req.origin[1])) for req in requests]
    destinations = [(Float64(req.destination[2]), Float64(req.destination[1])) for req in requests]
    all_points = vcat(collect(values(nodes)), origins, destinations, [depot_point], boundaries...)
    mean_lat = sum(point[2] for point in values(nodes)) / length(nodes)
    factor = cosd(mean_lat)
    xs = first.(all_points) .* factor
    ys = last.(all_points)
    min_x, max_x = extrema(xs)
    min_y, max_y = extrema(ys)
    width, margin = 1600, 85
    height = clamp(round(Int, width * (max_y - min_y) / max(max_x - min_x, eps()) + 150), 550, 1200)
    scale = min((width - 2margin) / max(max_x - min_x, eps()),
                (height - 2margin) / max(max_y - min_y, eps()))
    to_point(p) = Point((p[1] * factor - (min_x + max_x) / 2) * scale,
                        ((min_y + max_y) / 2 - p[2]) * scale + 15)

    mkpath(dirname(output_file))
    Drawing(width, height, output_file)
    origin()
    background("white")
    sethue("#b7c1c9")
    setline(0.65)
    for road in roads
        poly(to_point.(road), :stroke; close=false)
    end
    sethue("#577fa8")
    setopacity(0.28)
    setline(0.8)
    for (a, b) in zip(origins, destinations)
        line(to_point(a), to_point(b), :stroke)
    end
    if !isnothing(busline)
        setopacity(0.95)
        sethue("#1268a3")
        setline(3.2)
        for route in route_lines
            poly(to_point.(route), :stroke; close=false)
        end
        for stop in route_stops
            circle(to_point(stop), 3, :fill)
        end
    end
    sethue("#d8c895")
    setopacity(0.65)
    for poi in pois
        circle(to_point((Float64(poi.lon), Float64(poi.lat))), 2, :fill)
    end
    setopacity(1)
    sethue("#b56a18")
    for point in parking
        box(to_point(point), 16, 16, :fill)
    end
    sethue("#a33375")
    for point in charging
        center = to_point(point)
        poly([Point(center.x, center.y - 6), Point(center.x + 6, center.y),
              Point(center.x, center.y + 6), Point(center.x - 6, center.y)], :fill; close=true)
    end
    for (points, color) in ((origins, "#008f85"), (destinations, "#d96845"))
        sethue(color)
        for point in points
            circle(to_point(point), 3.5, :fill)
        end
    end
    sethue("#c62828")
    box(to_point(depot_point), 12, 12, :fill)
    sethue("#8356a6")
    setline(2.5)
    for boundary in boundaries
        poly(to_point.(boundary), :stroke; close=true)
    end
    sethue("#27343d")
    fontsize(23)
    text("$(basename(dirname(requests_file))) · $graph_name driving network", Point(-width / 2 + 35, -height / 2 + 42))
    fontsize(17)
    sethue("#008f85")
    circle(Point(-width / 2 + 38, height / 2 - 38), 5, :fill)
    sethue("#27343d")
    text("origins ($(length(requests)))", Point(-width / 2 + 52, height / 2 - 32))
    sethue("#d96845")
    circle(Point(-width / 2 + 255, height / 2 - 38), 5, :fill)
    sethue("#27343d")
    text("destinations ($(length(requests)))", Point(-width / 2 + 269, height / 2 - 32))
    sethue("#577fa8")
    line(Point(-width / 2 + 545, height / 2 - 38), Point(-width / 2 + 570, height / 2 - 38), :stroke)
    sethue("#27343d")
    text("straight OD", Point(-width / 2 + 581, height / 2 - 32))
    sethue("#d8c895")
    circle(Point(-width / 2 + 795, height / 2 - 38), 5, :fill)
    sethue("#27343d")
    text("POIs ($(length(pois)))", Point(-width / 2 + 809, height / 2 - 32))
    sethue("#c62828")
    box(Point(-width / 2 + 1000, height / 2 - 38), 10, 10, :fill)
    sethue("#27343d")
    text("depot", Point(-width / 2 + 1015, height / 2 - 32))
    sethue("#8356a6")
    line(Point(-width / 2 + 1160, height / 2 - 38), Point(-width / 2 + 1185, height / 2 - 38), :stroke)
    sethue("#27343d")
    text("service area", Point(-width / 2 + 1195, height / 2 - 32))
    if !isempty(parking)
        sethue("#b56a18")
        box(Point(-width / 2 + 640, height / 2 - 73), 10, 10, :fill)
        sethue("#27343d")
        text("parking ($(length(parking)))", Point(-width / 2 + 655, height / 2 - 67))
    end
    if !isempty(charging)
        sethue("#a33375")
        center = Point(-width / 2 + 870, height / 2 - 73)
        poly([Point(center.x, center.y - 7), Point(center.x + 7, center.y),
              Point(center.x, center.y + 7), Point(center.x - 7, center.y)], :fill; close=true)
        sethue("#27343d")
        text("charging ($(length(charging)))", Point(-width / 2 + 885, height / 2 - 67))
    end
    if !isnothing(busline)
        sethue("#1268a3")
        setline(3)
        line(Point(-width / 2 + 35, height / 2 - 73), Point(-width / 2 + 60, height / 2 - 73), :stroke)
        circle(Point(-width / 2 + 260, height / 2 - 73), 4, :fill)
        sethue("#27343d")
        text("bus $busline (stops linked)", Point(-width / 2 + 70, height / 2 - 67))
        text("bus stops", Point(-width / 2 + 272, height / 2 - 67))
    end
    finish()
    return output_file
end

end
