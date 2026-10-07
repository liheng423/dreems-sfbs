# Corridor and demand-generation settings. Edit here, then rerun generate.jl.
# Sample passenger preferences first, filter corridor feasibility, then select nested scenarios.

const DEBUG = true  # Write debug/rejected_candidates_<dataset>.debug.json when enabled.

# Uniform service dwell at every logical stop, in nonnegative whole minutes.
# This is a model assumption, independent of GTFS arrival/departure equality.
const DWELL_MIN = 0

const SEED = 42  # Seed for reproducible candidate sampling.
const CAND_COUNT_PER_PATTERN = 4_000  # Raw unlabeled attempts per route pattern.
const PICKUP_HALF_WIDTH_MIN = 5   # Desired pickup time ± this many minutes.

# Pre-bookings are sampled in whole days; dynamic leads in whole minutes.
# Dynamic bookings must also occur after the pattern's service starts.
const PREBOOK_LEAD_DAYS = 1:3  # Inclusive pre-booking lead range in whole days.
const DYN_LEAD_MIN = 5:30  # Inclusive dynamic booking lead range in whole minutes.

# Scenario proportions in [0, 1]; complementary types receive the remainder.
const PREBOOK_SHARE = 0.5  # Dynamic share = 1 - PREBOOK_SHARE.
const ELECTRIC_SHARE = 0.5  # Conventional share = 1 - ELECTRIC_SHARE.

# Totals are balanced across route patterns within each booking type.
# Each cell's allocation must fit within CAND_COUNT_PER_PATTERN.
const SCEN_REQ_COUNTS = (
    "low" => 50,  # Low-demand scenario name and total request count.
    "base" => 100,  # Base-demand scenario name and total request count.
    "high" => 200,  # High-demand scenario name and total request count.
)

# Normal pickup-time distribution relative to each pattern's service period.
# Defaults put the mean at midday and roughly six standard deviations in the period.
const DES_MEAN_FRACTION = 0.5
const DES_STD_FRACTION = 1 / 6
const TERM_BUFFER_MIN = 5  # Finish the mandatory corridor before service closes.
