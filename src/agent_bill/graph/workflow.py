"""LangGraph definition for the multi-agent workflow."""

from langgraph.graph import StateGraph, END

from agent_bill.graph.state import AgentState
from agent_bill.agents.bill_validator import bill_validator_node
from agent_bill.agents.market_research import market_research_node
from agent_bill.agents.advisor import advisor_node


def build_workflow() -> StateGraph:
    """Build and compile the workflow graph."""
    workflow = StateGraph(AgentState)

    workflow.add_node("bill_validator", bill_validator_node)
    workflow.add_node("market_research", market_research_node)
    workflow.add_node("advisor", advisor_node)

    workflow.set_entry_point("bill_validator")
    workflow.add_edge("bill_validator", "market_research")
    workflow.add_edge("market_research", "advisor")
    workflow.add_edge("advisor", END)

    return workflow.compile()
