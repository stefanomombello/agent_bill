from pydantic import BaseModel, Field

from agent_bill.models.bill import ConsumptionProfile
from agent_bill.models.cadastral import CadastralInfo
from agent_bill.models.offer import OfferComparison


class AdvisoryReport(BaseModel):
    """Final report with recommendations for the client."""

    client_name: str = Field(default="Client")
    consumption_profile: ConsumptionProfile | None = None
    cadastral_info: CadastralInfo | None = None
    electricity_comparison: OfferComparison | None = None
    gas_comparison: OfferComparison | None = None
    recommendations: str = Field(
        default="", description="Recommendations in Markdown format"
    )
    total_potential_saving: float | None = None
