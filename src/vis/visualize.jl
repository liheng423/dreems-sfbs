#!/usr/bin/env julia

"""Render route-pattern scenario maps and an overview PDF.

Usage:
    julia --project=. src/vis/visualize.jl
    julia --project=. src/vis/visualize.jl [instances_dir] [output_dir]
    julia --project=. src/vis/visualize.jl --label-stops

Each scenario produces one PNG per route pattern. The overview PDF places the
three demand levels side by side for all patterns. No city-centre pair or
fleet section is assumed.
"""

using JSON3
ENV["GKSwstype"] = "100"  # Render to files without trying to open a desktop window.
using Plots

const SCRIPT_DIR = @__DIR__
const BUS550_ROOT = dirname(dirname(SCRIPT_DIR))
const DEFAULT_INSTANCE_DIR = joinpath(BUS550_ROOT, "data", "instances")
const DEFAULT_OUTPUT_DIR = joinpath(BUS550_ROOT, "visualizations")

# Fixed colors shared by individual maps and the overview.
const COLORS = (
    route=:steelblue4,
    prebooked=:dodgerblue3,
    dynamic=:darkorange2,
    optional=:gray65,
    mandatory=:black,
    terminal=:forestgreen,
)

request_color(colors, book_type::String) =
    book_type == "prebooked" ? colors.prebooked : colors.dynamic

function stop_xy(net, stop_id)
    xy = net["coordinates"][string(stop_id)]
    return Float64(xy[1]), Float64(xy[2])
end

function scen_reqs(inst, pattern)
    [(kind=book_type, org=Int(req["origin"]), dst=Int(req["destination"]))
     for book_type in ("prebooked", "dynamic")
     for req in values(inst["requests"][book_type])
     if req["route_id"] == pattern["route_id"] && req["pattern_id"] == pattern["pattern_id"]]
end

function pattern_title(inst, pattern, req_count)
    scen = String(inst["config"]["scenario"])
    line = String(inst["config"]["dataset"])
    date = String(inst["config"]["service_date"])
    return "Line $line · $scen demand · $date\n$(pattern["label"]) ($req_count requests)"
end

function draw_reqs!(plt, inst, reqs)
    seen = Set{String}()
    for req in reqs
        org_xy = stop_xy(inst["network"], req.org)
        dst_xy = stop_xy(inst["network"], req.dst)
        label = req.kind in seen ? "" : "$(req.kind) OD"
        push!(seen, req.kind)
        plot!(plt, [org_xy[1], dst_xy[1]], [org_xy[2], dst_xy[2]];
              color=request_color(COLORS, req.kind), linewidth=0.8, alpha=0.18, label=label)
    end
end

function draw_stops!(plt, net, pattern; lbl_stops::Bool=false)
    stop_ids = Int.(pattern["stops"])
    mand_ids = Set(Int.(net["mandatory_stops"]))
    term_ids = Set(Int.(pattern["terminal_ids"]))
    opt_ids = [id for id in stop_ids if !(id in mand_ids)]
    mand_stop_ids = [id for id in stop_ids if id in mand_ids && !(id in term_ids)]

    function scatter_ids(ids, color, marker, size, label)
        isempty(ids) && return
        xy = [stop_xy(net, id) for id in ids]
        scatter!(plt, first.(xy), last.(xy); color=color, marker=marker,
                 markersize=size, markerstrokewidth=0.7,
                 markerstrokecolor=:white, label=label)
    end

    scatter_ids(opt_ids, COLORS.optional, :circle, 4.1, "optional stop")
    scatter_ids(mand_stop_ids, COLORS.mandatory, :diamond, 5.4, "mandatory anchor / interchange")
    scatter_ids(collect(term_ids), COLORS.terminal, :star5, 8.2, "terminal")

    if lbl_stops
        for (seq, id) in enumerate(stop_ids)
            x, y = stop_xy(net, id)
            annotate!(plt, x, y, text(string(seq), 7, :left, :bottom))
        end
    end
end

function plot_pattern(inst, pattern; compact::Bool=false, lbl_stops::Bool=false)
    net = inst["network"]
    stop_ids = Int.(pattern["stops"])
    xy = [stop_xy(net, id) for id in stop_ids]
    reqs = scen_reqs(inst, pattern)
    scen = String(inst["config"]["scenario"])
    pattern_label = String(pattern["label"])
    req_count = length(reqs)
    overview_title = "$scen · n=$req_count\n$(replace(pattern_label, " -> " => " → "))"
    plt = plot(; title=compact ? overview_title : pattern_title(inst, pattern, req_count),
             xlabel=compact ? "" : "longitude",
             ylabel=compact ? "" : "latitude",
             legend=compact ? false : :outerright,
             grid=true, framestyle=:box, aspect_ratio=:equal,
             size=compact ? (560, 390) : (1150, 800),
             titlefontsize=compact ? 10 : 12,
             guidefontsize=9, tickfontsize=compact ? 6 : 8,
             margin=compact ? 2 * Plots.mm : 5 * Plots.mm)
    plot!(plt, first.(xy), last.(xy); color=COLORS.route, linewidth=2.2,
          alpha=0.9, label="scheduled stop order")
    draw_reqs!(plt, inst, reqs)
    draw_stops!(plt, net, pattern; lbl_stops=lbl_stops && !compact)
    return plt
end

function main(args=ARGS)
    pos_args = filter(arg -> !startswith(arg, "--"), args)
    lbl_stops = "--label-stops" in args
    inst_dir = length(pos_args) >= 1 ? abspath(pos_args[1]) : DEFAULT_INSTANCE_DIR
    out_dir = length(pos_args) >= 2 ? abspath(pos_args[2]) : DEFAULT_OUTPUT_DIR
    scen_paths = sort(filter(path -> endswith(path, ".json"), readdir(inst_dir; join=true)))
    insts = [JSON3.read(read(path, String)) for path in scen_paths]
    mkpath(out_dir)

    ovw = Plots.Plot[]
    for inst in insts
        scen = String(inst["config"]["scenario"])
        for (pattern_idx, pattern) in enumerate(inst["network"]["patterns"])
            dataset = inst["config"]["dataset"]
            out_path = joinpath(out_dir, "$(dataset)_$(scen)_pattern_$(pattern_idx).png")
            savefig(plot_pattern(inst, pattern; lbl_stops=lbl_stops), out_path)
            println("Saved $out_path")
            push!(ovw, plot_pattern(inst, pattern; compact=true))
        end
    end
    ovw_plot = plot(ovw...; layout=(length(insts), length(first(insts)["network"]["patterns"])),
                         size=(710 * length(first(insts)["network"]["patterns"]), 500 * length(insts)),
                         plot_title="Scheduled bus network and demand scenarios")
    pdf_path = joinpath(out_dir, "network_scenarios_overview.pdf")
    savefig(ovw_plot, pdf_path)
    println("Saved $pdf_path")
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
