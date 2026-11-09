"""Shared state for the LangGraph workflow."""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from agent_bill.models.analysis import AnalysisMode, NewSupplyRequirements
from agent_bill.models.bill import BillData, ConsumptionProfile
from agent_bill.models.cadastral import CadastralInfo


class AgentState(TypedDict, total=False):
    """State shared by all graph nodes."""

    # Input
    client_name: str
    analysis_mode: AnalysisMode
    bills: list[BillData]
    cadastral_info: CadastralInfo | None
    new_supply_requirements: NewSupplyRequirements | None

    # Accumulated LangGraph messages
    messages: Annotated[list, add_messages]

    # Intermediate outputs
    consumption_profile: ConsumptionProfile | None
    validation_notes: str
    market_research: str

    # Final output
    final_report: str
