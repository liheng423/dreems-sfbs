# Representative energy assumptions from Jablonski et al., NEIS 2023.
# Electric: Table 1, 12 m eCitaro with 396 kWh battery and hybrid heating,
# measured at 20–22 °C. Conventional: midpoint of the 3.90–4.98 kWh/km
# fuel-energy range cited from earlier studies in the introduction.
const FLEET_PROFILES = Dict(
    "electric" => (
        energy_source="battery",
        energy_kwh_per_km=0.87,
        passenger_capacity=88,
        battery_capacity_kwh=396,
        heating_strategy="hybrid",
        energy_reference="Jablonski et al. (2023), Table 1; 20–22 °C",
    ),
    "conventional" => (
        energy_source="fuel energy equivalent",
        energy_kwh_per_km=4.44,
        energy_reference="Jablonski et al. (2023), introduction; midpoint of cited 3.90–4.98 kWh/km range",
    ),
)
