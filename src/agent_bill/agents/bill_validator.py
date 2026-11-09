"""BillValidatorAgent: validate and normalize user-provided utility bill data."""

from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama

from agent_bill.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from agent_bill.graph.state import AgentState
from agent_bill.tools.energy_calc import build_consumption_profile, estimate_new_supply_profile

SYSTEM_PROMPT = """You are an expert analyst of Italian energy bills.
Your tasks are to:
1. Check bill data for consistency (e.g. consumption vs. costs and valid billing periods)
2. Flag obvious anomalies (costs too high or low for the reported consumption)
3. Produce a structured summary of the client's consumption profile

Determine indicative reference prices for the current Italian market:
(e.g. electricity: 0.10-0.30 €/kWh, gas: 0.80-1.50 €/Smc for May 2026)

Respond in English. Be concise and precise."""


def bill_validator_node(state: AgentState) -> dict:
    """Graph node: validate bills and build the consumption profile."""
    bills = state.get("bills", [])

    if not bills:
        cadastral = state.get("cadastral_info")
        requirements = state.get("new_supply_requirements")
        if not cadastral or not requirements:
            return {
                "messages": [{"role": "assistant", "content": "Insufficient data for estimation."}],
                "validation_notes": "Property data and new supply requirements are needed.",
            }

        profile = estimate_new_supply_profile(cadastral, requirements)
        notes = " ".join(profile.estimation_notes)
        validation_notes = (
            "New supply without historical data: consumption figures are estimates, not readings. "
            f"Electricity: {profile.avg_monthly_kwh or 'not requested'} kWh/month; "
            f"gas: {profile.avg_monthly_smc or 'not requested'} Smc/month. {notes}"
        )
        return {
            "messages": [{"role": "assistant", "content": validation_notes}],
            "consumption_profile": profile,
            "validation_notes": validation_notes,
        }

    profile = build_consumption_profile(bills)

    bills_summary = []
    for i, bill in enumerate(bills, 1):
        consumption = bill.consumption_kwh or bill.consumption_smc or 0
        unit = "kWh" if bill.utility_type == "electricity" else "Smc"
        cost_per_unit = bill.cost_per_unit or 0
        energy_price = bill.energy_price_per_unit or "N/A"
        bills_summary.append(
            f"Bill {i}: {bill.utility_type.value} - {bill.provider} - "
            f"Period: {bill.period_start}/{bill.period_end} - "
            f"Consumption: {consumption} {unit} - Total cost: €{bill.total_cost_eur} - "
            f"Total €/{unit}: {cost_per_unit} - "
            f"Energy commodity price: €{energy_price}/{unit} - "
            f"Energy commodity: €{bill.energy_cost_eur or 'N/A'} - "
            f"Transport/network: €{bill.transport_cost_eur or 'N/A'} - "
            f"System charges: €{bill.system_charges_eur or 'N/A'} - "
            f"Taxes: €{bill.taxes_eur or 'N/A'}"
        )

    cadastral = state.get("cadastral_info")
    cadastral_text = ""
    if cadastral:
        cadastral_text = (
            f"\nProperty data: {cadastral.property_type}, {cadastral.surface_sqm} sqm, "
            f"{cadastral.residents} residents, heating {cadastral.heating_type}, "
            f"energy rating {cadastral.energy_class or 'unknown'}"
        )

    user_msg = (
        "Analyze these bills and flag any anomalies:\n\n"
        + "\n".join(bills_summary)
        + cadastral_text
        + f"\n\nAverage monthly electricity consumption: {profile.avg_monthly_kwh or 'N/A'} kWh"
        + f"\nAverage monthly gas consumption: {profile.avg_monthly_smc or 'N/A'} Smc"
        + f"\nEstimated annual cost: €{profile.total_annual_cost or 'N/A'}"
    )

    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), {"role": "user", "content": user_msg}])

    return {
        "messages": [{"role": "assistant", "content": response.content}],
        "consumption_profile": profile,
        "validation_notes": response.content,
    }
