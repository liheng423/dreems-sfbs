#!/usr/bin/env julia

"""Render direction-aware Route 550 scenario maps and an overview PDF.

Usage:
    julia --project=. src/vis/visualize.jl
    julia --project=. src/vis/visualize.jl [instances_dir] [output_dir]
    julia --project=. src/vis/visualize.jl --label-stops

Each scenario produces one PNG per direction. The overview PDF places the
three demand levels side by side for both directions. No city-centre pair or
fleet section is assumed.
"""

using JSON3
ENV["GKSwstype"] = "100"  # Render to files without trying to open a desktop window.
using Plots

const SCRIPT_DIR = @__DIR__
const BUS550_ROOT = dirname(SCRIPT_DIR)
const DEFAULT_INSTANCE_DIR = joinpath(BUS550_ROOT, "data", "instances")
const DEFAULT_OUTPUT_DIR = joinpath(BUS550_ROOT, "visualizations")

struct ColorPalette
    route::Symbol
    prebooked::Symbol
    dynamic::Symbol
    optional::Symbol
    mandatory::Symbol
    terminal::Symbol
end

request_color(colors::ColorPalette, booking_type::String) =
    booking_type == "prebooked" ? colors.prebooked : colors.dynamic

const COLORS = ColorPalette(
    :steelblue4,
    :dodgerblue3,
    :darkorange2,
    :gray65,
    :black,
    :forestgreen,
)

function stop_xy(net, stop_id)
    xy = net["coordinates"][string(stop_id)]
    return Float64(xy[1]), Float64(xy[2])
end

function scen_reqs(inst, dir_id)
    [(kind=book_type, org=Int(req["origin"]), dst=Int(req["destination"]))
     for book_type in ("prebooked", "dynamic")
     for req in values(inst["requests"][book_type])
     if String(req["direction"]) == dir_id]
end

function dir_title(inst, dir, req_count)
    scen = String(inst["config"]["scenario"])
    line = String(inst["config"]["route_short_name"])
    date = String(inst["config"]["service_date"])
    return "Line $line · $scen demand · $date\n$(dir["label"]) ($req_count requests)"
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

function draw_stops!(plt, net, dir; lbl_stops::Bool=false)
    stop_ids = Int.(dir["stops"])
    mand_ids = Set(Int.(net["mandatory_stops"]))
    term_ids = Set(Int.(dir["terminal_ids"]))
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

function plot_dir(inst, dir; compact::Bool=false, lbl_stops::Bool=false)
    net = inst["network"]
    stop_ids = Int.(dir["stops"])
    xy = [stop_xy(net, id) for id in stop_ids]
    reqs = scen_reqs(inst, String(dir["direction_id"]))
    scen = String(inst["config"]["scenario"])
    dir_label = String(dir["label"])
    req_count = length(reqs)
    overview_title = "$scen · n=$req_count\n$(replace(dir_label, " -> " => " → "))"
    plt = plot(; title=compact ? overview_title : dir_title(inst, dir, req_count),
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
    draw_stops!(plt, net, dir; lbl_stops=lbl_stops && !compact)
    return plt
end

function main(args=ARGS)
    pos_args = filter(arg -> !startswith(arg, "--"), args)
    lbl_stops = "--label-stops" in args
    inst_dir = length(pos_args) >= 1 ? abspath(pos_args[1]) : DEFAULT_INSTANCE_DIR
    out_dir = length(pos_args) >= 2 ? abspath(pos_args[2]) : DEFAULT_OUTPUT_DIR
    scen_paths = [joinpath(inst_dir, "550_$(name).json") for name in ("low", "base", "high")]
    insts = [JSON3.read(read(path, String)) for path in scen_paths]
    mkpath(out_dir)

    ovw = Plots.Plot[]
    for (scen_idx, scen) in enumerate(("low", "base", "high"))
        inst = insts[scen_idx]
        for dir in inst["network"]["directions"]
            dir_id = String(dir["direction_id"])
            out_path = joinpath(out_dir, "550_$(scen)_direction_$(dir_id).png")
            savefig(plot_dir(inst, dir; lbl_stops=lbl_stops), out_path)
            println("Saved $out_path")
            push!(ovw, plot_dir(inst, dir; compact=true))
        end
    end
    ovw_plot = plot(ovw...; layout=(3, 2), size=(1420, 1510),
                         plot_title="Route 550 · scheduled corridor and demand scenarios")
    pdf_path = joinpath(out_dir, "route550_scenarios_overview.pdf")
    savefig(ovw_plot, pdf_path)
    println("Saved $pdf_path")
end

if abspath(PROGRAM_FILE) == @__FILE__
    main()
end
