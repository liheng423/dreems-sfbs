"""Build direction records with distinct logical stop IDs for each GTFS stop pattern."""
function build_dirs(pats)
    dirs = NamedTuple[]
    next_logi_id = 1
    for pat in pats
        src_ids = String.(pat["stop_ids"])
        logi_ids = collect(next_logi_id:(next_logi_id + length(src_ids) - 1))
        next_logi_id += length(src_ids)
        push!(dirs, (
            direction_id=String(pat["direction_id"]),  # GTFS direction ID, distinguishing outbound and return service.
            pattern_id=String(pat["pattern_id"]),  # GTFS pattern ID identifying this ordered stop sequence.
            label=String(pat["label"]),  # Readable direction label from the crawler.
            stops=logi_ids,  # Logical stop IDs in travel order.
            source_stop_ids=src_ids,  # Original GTFS stop IDs aligned with the logical IDs.
            terminal_ids=[first(logi_ids), last(logi_ids)],  # Logical IDs of the first and last stops.
        ))
    end
    return dirs
end

"""Return the direction owning a logical stop ID in the network."""
stop_dir(net, stop_id) = only(dir for dir in net.directions if stop_id in dir.stops)
