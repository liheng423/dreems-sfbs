"""Return the route pattern owning a logical stop occurrence in the network."""
stop_pattern(net, stop_id) = only(pattern for pattern in net.patterns if stop_id in pattern.stops)

"""Resolve a logical stop occurrence to its original GTFS stop ID."""
src_stop_id(net, stop_id) = net.source_stop_ids[string(stop_id)]

"""Return all logical occurrences of a physical stop, including repeated visits."""
logi_stop_ids(net, src_id) = [id for pattern in net.patterns for id in pattern.stops
                            if src_stop_id(net, id) == src_id]

"""Accept one normalized route snapshot or an array of snapshots from the same feed/day."""
route_crawls(crawl) = crawl isa AbstractVector ? crawl : [crawl]
