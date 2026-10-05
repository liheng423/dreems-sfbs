# Demand-generation settings. Edit here, then rerun generate.jl.
# Sampling is uniform over feasible trip/OD pairs, with nested scenario samples.

const SEED = 42  # Seed for reproducible candidate sampling.
const CAND_COUNT_PER_CELL = 2_000  # Each booking-type/direction cell.
const PICKUP_HALF_WIDTH_MIN = 5   # Desired pickup time ± this many minutes.

# Pre-bookings are sampled in whole days; dynamic leads in whole minutes.
# Dynamic bookings must also occur after the direction's service starts.
const PREBOOK_LEAD_DAYS = 1:3  # Inclusive pre-booking lead range in whole days.
const DYN_LEAD_MIN = 5:30  # Inclusive dynamic booking lead range in whole minutes.

# Even totals, balanced across booking types and directions 0/1.
# Each cell's allocation must fit within CAND_COUNT_PER_CELL.
const SCEN_REQ_COUNTS = (
    "low" => 50,  # Low-demand scenario name and total request count.
    "base" => 100,  # Base-demand scenario name and total request count.
    "high" => 200,  # High-demand scenario name and total request count.
)
