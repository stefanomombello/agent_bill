from enum import Enum

from pydantic import BaseModel, Field

from agent_bill.models.bill import UtilityType


class AnalysisMode(str, Enum):
    BILL_COMPARISON = "bill_comparison"
    NEW_SUPPLY = "new_supply"


class EnergySource(str, Enum):
    GAS = "gas"
    HEAT_PUMP = "heat_pump"
    ELECTRICITY = "electricity"
    CENTRALIZED = "centralized"
    OTHER = "other"


class NewSupplyRequirements(BaseModel):
    """Requirements for a new supply without historical consumption data."""

    utility_types: list[UtilityType] = Field(min_length=1)
    heating_source: EnergySource = EnergySource.OTHER
    hot_water_source: EnergySource = EnergySource.OTHER
    gas_for_cooking: bool = False
    estimated_annual_kwh: float | None = Field(default=None, ge=0)
    estimated_annual_smc: float | None = Field(default=None, ge=0)
    notes: str = ""