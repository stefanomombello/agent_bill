from pydantic import BaseModel, Field

from agent_bill.models.bill import UtilityType


class MarketOffer(BaseModel):
    """An offer found on the market."""

    provider: str = Field(description="Provider name")
    offer_name: str = Field(description="Commercial offer name")
    utility_type: UtilityType
    price_per_unit: float | None = Field(
        default=None, description="Price per kWh or Smc in EUR"
    )
    monthly_fixed_cost: float | None = Field(
        default=None, description="Monthly fixed cost in EUR"
    )
    estimated_annual_cost: float | None = Field(
        default=None, description="Estimated annual cost in EUR"
    )
    source_url: str = Field(default="", description="Source URL")
    notes: str = Field(default="", description="Additional notes")


class OfferComparison(BaseModel):
    """Comparison between the current offer and market offers."""

    current_provider: str
    current_annual_cost: float
    best_offer: MarketOffer | None = None
    potential_saving_eur: float | None = None
    all_offers: list[MarketOffer] = Field(default_factory=list)
