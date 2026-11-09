from enum import Enum
from pydantic import BaseModel, Field


class UtilityType(str, Enum):
    ELECTRICITY = "electricity"
    GAS = "gas"


class BillData(BaseModel):
    """Data extracted from an electricity or gas bill."""

    utility_type: UtilityType
    provider: str = Field(description="Provider name (e.g. Enel, Eni, A2A)")
    contract_type: str = Field(
        default="", description="Contract type (free market / regulated tariff)"
    )
    period_start: str = Field(description="Billing period start (YYYY-MM-DD)")
    period_end: str = Field(description="Billing period end (YYYY-MM-DD)")

    # Consumption
    consumption_kwh: float | None = Field(
        default=None, description="Consumption in kWh (electricity only)"
    )
    consumption_smc: float | None = Field(
        default=None, description="Consumption in Smc (gas only)"
    )

    # Costs
    total_cost_eur: float = Field(description="Total bill cost in EUR")
    energy_cost_eur: float | None = Field(
        default=None, description="Energy commodity cost in EUR"
    )
    energy_price_per_unit: float | None = Field(
        default=None,
        description="Energy commodity unit price (€/kWh or €/Smc)",
    )
    transport_cost_eur: float | None = Field(
        default=None, description="Transport/meter management cost in EUR"
    )
    system_charges_eur: float | None = Field(
        default=None, description="System charges in EUR"
    )
    taxes_eur: float | None = Field(default=None, description="Taxes (excise duty + VAT) in EUR")

    # Identifiers
    pod_pdr: str = Field(
        default="", description="POD code (electricity) or PDR code (gas)"
    )
    power_kw: float | None = Field(
        default=None, description="Contracted power in kW (electricity only)"
    )

    @property
    def cost_per_unit(self) -> float | None:
        """Total unit cost per kWh or Smc (all charges included)."""
        consumption = self.consumption_kwh or self.consumption_smc
        if consumption and consumption > 0:
            return round(self.total_cost_eur / consumption, 4)
        return None

    @property
    def fixed_costs_eur(self) -> float:
        """Provider-independent fixed costs: network + system charges + taxes."""
        return (
            (self.transport_cost_eur or 0)
            + (self.system_charges_eur or 0)
            + (self.taxes_eur or 0)
        )


class ConsumptionProfile(BaseModel):
    """The client's aggregated consumption profile."""

    bills: list[BillData] = Field(default_factory=list)
    avg_monthly_kwh: float | None = None
    avg_monthly_smc: float | None = None
    avg_monthly_cost_electricity: float | None = None
    avg_monthly_cost_gas: float | None = None
    total_annual_cost: float | None = None
    is_estimated: bool = False
    estimation_notes: list[str] = Field(default_factory=list)
