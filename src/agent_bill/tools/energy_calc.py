"""Utilities for energy calculations and tariff comparisons."""

from agent_bill.models.analysis import EnergySource, NewSupplyRequirements
from agent_bill.models.bill import BillData, ConsumptionProfile, UtilityType
from agent_bill.models.cadastral import CadastralInfo


HEATING_DEMAND_KWH_SQM = {
    "A1": 30,
    "A2": 25,
    "A3": 20,
    "A4": 15,
    "B": 45,
    "C": 70,
    "D": 90,
    "E": 120,
    "F": 160,
    "G": 200,
}


def build_consumption_profile(bills: list[BillData]) -> ConsumptionProfile:
    """Build an aggregated consumption profile from bills."""
    elec_bills = [b for b in bills if b.utility_type == UtilityType.ELECTRICITY]
    gas_bills = [b for b in bills if b.utility_type == UtilityType.GAS]

    profile = ConsumptionProfile(bills=bills)

    if elec_bills:
        total_kwh = sum(b.consumption_kwh or 0 for b in elec_bills)
        total_cost_e = sum(b.total_cost_eur for b in elec_bills)
        months_e = len(elec_bills)
        profile.avg_monthly_kwh = round(total_kwh / months_e, 1)
        profile.avg_monthly_cost_electricity = round(total_cost_e / months_e, 2)

    if gas_bills:
        total_smc = sum(b.consumption_smc or 0 for b in gas_bills)
        total_cost_g = sum(b.total_cost_eur for b in gas_bills)
        months_g = len(gas_bills)
        profile.avg_monthly_smc = round(total_smc / months_g, 1)
        profile.avg_monthly_cost_gas = round(total_cost_g / months_g, 2)

    total = 0.0
    if profile.avg_monthly_cost_electricity:
        total += profile.avg_monthly_cost_electricity * 12
    if profile.avg_monthly_cost_gas:
        total += profile.avg_monthly_cost_gas * 12
    profile.total_annual_cost = round(total, 2) if total > 0 else None

    return profile


def estimate_new_supply_profile(
    cadastral: CadastralInfo,
    requirements: NewSupplyRequirements,
) -> ConsumptionProfile:
    """Estimate indicative consumption for a new supply without historical data."""
    residents = max(cadastral.residents, 1)
    surface_sqm = max(cadastral.surface_sqm, 1)
    energy_class = cadastral.energy_class.strip().upper()
    heating_demand = HEATING_DEMAND_KWH_SQM.get(energy_class, 100) * surface_sqm
    notes = [
        "Indicative estimate based on floor area, occupants, energy rating and declared usage.",
    ]
    if energy_class not in HEATING_DEMAND_KWH_SQM:
        notes.append("Unknown energy rating: assumed heating demand of 100 kWh/sqm per year.")

    profile = ConsumptionProfile(is_estimated=True, estimation_notes=notes)

    if UtilityType.ELECTRICITY in requirements.utility_types:
        annual_kwh = requirements.estimated_annual_kwh
        if annual_kwh is None:
            annual_kwh = 700 + (450 * residents) + (4 * surface_sqm)
            if requirements.heating_source == EnergySource.HEAT_PUMP:
                annual_kwh += heating_demand / 3
            elif requirements.heating_source == EnergySource.ELECTRICITY:
                annual_kwh += heating_demand
            if requirements.hot_water_source in {EnergySource.ELECTRICITY, EnergySource.HEAT_PUMP}:
                annual_kwh += 500 * residents
        else:
            notes.append("Annual electricity consumption provided by the user.")
        profile.avg_monthly_kwh = round(annual_kwh / 12, 1)

    if UtilityType.GAS in requirements.utility_types:
        annual_smc = requirements.estimated_annual_smc
        if annual_smc is None:
            annual_smc = 0.0
            if requirements.heating_source == EnergySource.GAS:
                annual_smc += heating_demand / 10.7
            if requirements.hot_water_source == EnergySource.GAS:
                annual_smc += 70 * residents
            if requirements.gas_for_cooking:
                annual_smc += 35 * residents
        else:
            notes.append("Annual gas consumption provided by the user.")
        profile.avg_monthly_smc = round(annual_smc / 12, 1)

    return profile


def estimate_annual_saving(
    current_annual_cost: float,
    new_price_per_unit: float,
    annual_consumption: float,
    new_fixed_monthly: float = 0.0,
) -> float:
    """Estimate annual savings from switching to a new offer."""
    new_annual = (new_price_per_unit * annual_consumption) + (new_fixed_monthly * 12)
    return round(current_annual_cost - new_annual, 2)


def estimate_saving_energy_only(
    current_energy_cost: float,
    new_price_per_unit: float,
    consumption: float,
) -> float:
    """Estimate savings by comparing ONLY the energy commodity item.

    Network costs, system charges and taxes remain unchanged.
    """
    new_energy_cost = new_price_per_unit * consumption
    return round(current_energy_cost - new_energy_cost, 2)
