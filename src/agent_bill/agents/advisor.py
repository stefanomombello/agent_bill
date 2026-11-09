"""AdvisorAgent: generate the final report with recommendations for the client."""

from datetime import date

from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama

from agent_bill.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from agent_bill.graph.state import AgentState
from agent_bill.models.bill import UtilityType

SYSTEM_PROMPT = """You are an expert energy advisor for the Italian market.
Produce a clear, professional Markdown report for the client.

The report must include:
1. **Current situation summary** - provider, average consumption, estimated annual cost
2. **Bill cost breakdown** - detailed table: energy commodity, transport/network, system charges,
   taxes, and the CORRECT TOTAL (verified sum)
3. **Energy commodity price analysis** - compare the €/kWh or €/Smc price with market offers
4. **Alternative offers** - table: provider, offer, price per kWh, estimated monthly cost, offer URL
5. **Savings calculation** - replace ONLY the energy commodity item with the offer's price,
   keep transport, system charges and taxes unchanged, and calculate the new total
6. **Final recommendation** - what to do, with estimated annual savings in €

IMPORTANT RULES:
- The SUM of the cost breakdown items (energy commodity + transport + charges + taxes) MUST equal the total
- Calculate savings ONLY from the difference in energy commodity prices
- Network costs, system charges and taxes are the SAME for all providers (regulated by ARERA)
- ALWAYS distinguish these two metrics:
    1) "Energy commodity price" = unit price of the energy component alone (€/kWh or €/Smc)
    2) "All-inclusive total unit cost" = total bill cost / consumption (including network, charges, taxes)
- Do NOT use "current average price" when referring to the all-inclusive cost.
- ALWAYS include URLs for recommended offers
- Report ONLY real, verifiable offers already included in the market research section.
- NEVER invent providers, offers, prices, URLs or placeholders such as "Provider A", "Offer 1" or "#".
- If no verifiable better offer was found, state this explicitly and do not simulate savings with hypothetical offers.
- If no verifiable better offer was found, the "Alternative offers" section must contain ONLY
    a message stating that no better offer was found, WITHOUT offer tables or lists.
- For a NEW SUPPLY without bills, replace the current summary, breakdown and savings calculation
    with: estimated consumption profile, estimation assumptions, offer comparison and estimated annual cost.
- For a NEW SUPPLY, do not invent a current provider, regulated costs or savings against past usage.
- Always label projected consumption and costs as "estimates".
- Use Markdown tables for comparisons
- Respond in English. Be direct and precise with numbers."""


def advisor_node(state: AgentState) -> dict:
    """Graph node: produce the final report with recommendations."""
    profile = state.get("consumption_profile")
    cadastral = state.get("cadastral_info")
    validation = state.get("validation_notes", "")
    market = state.get("market_research", "")
    client_name = state.get("client_name", "Client")
    requirements = state.get("new_supply_requirements")

    context_parts = [f"Report date: {date.today().isoformat()}\nClient: {client_name}\n"]

    if cadastral:
        context_parts.append(
            f"Property: {cadastral.property_type}, {cadastral.surface_sqm} sqm, "
            f"{cadastral.city} ({cadastral.province}), {cadastral.residents} residents, "
            f"heating: {cadastral.heating_type}, "
            f"energy rating: {cadastral.energy_class or 'unknown'}\n"
        )

    if profile:
        context_parts.append(
            f"Consumption profile:\n"
            f"- Monthly electricity average: {profile.avg_monthly_kwh or 'N/A'} kWh "
            f"(€{profile.avg_monthly_cost_electricity or 'N/A'}/month)\n"
            f"- Monthly gas average: {profile.avg_monthly_smc or 'N/A'} Smc "
            f"(€{profile.avg_monthly_cost_gas or 'N/A'}/month)\n"
            f"- Estimated annual cost: €{profile.total_annual_cost or 'N/A'}\n"
        )

    bills = state.get("bills", [])
    elec_bills = [b for b in bills if b.utility_type == UtilityType.ELECTRICITY]
    gas_bills = [b for b in bills if b.utility_type == UtilityType.GAS]

    if elec_bills:
        b = elec_bills[0]
        consumption = b.consumption_kwh or 0
        energy_unit_price = b.energy_price_per_unit
        if energy_unit_price is None and consumption > 0 and b.energy_cost_eur is not None:
            energy_unit_price = round(b.energy_cost_eur / consumption, 4)

        context_parts.append(
            f"ELECTRICITY data for the cost breakdown:\n"
            f"energy commodity: €{b.energy_cost_eur or 0:.2f}, "
            f"transport: €{b.transport_cost_eur or 0:.2f}, "
            f"system charges: €{b.system_charges_eur or 0:.2f}, "
            f"taxes: €{b.taxes_eur or 0:.2f}, "
            f"fixed costs: €{b.fixed_costs_eur or 0:.2f}, "
            f"TOTAL: €{b.total_cost_eur or 0:.2f}\n"
            f"Energy commodity price: €{energy_unit_price if energy_unit_price is not None else 0:.4f}/kWh\n"
        )

    if gas_bills:
        b = gas_bills[0]
        consumption = b.consumption_smc or 0
        energy_unit_price = b.energy_price_per_unit
        if energy_unit_price is None and consumption > 0 and b.energy_cost_eur is not None:
            energy_unit_price = round(b.energy_cost_eur / consumption, 4)

        context_parts.append(
            f"GAS data for the cost breakdown:\n"
            f"gas commodity: €{b.energy_cost_eur or 0:.2f}, "
            f"transport: €{b.transport_cost_eur or 0:.2f}, "
            f"system charges: €{b.system_charges_eur or 0:.2f}, "
            f"taxes: €{b.taxes_eur or 0:.2f}, "
            f"fixed costs: €{b.fixed_costs_eur or 0:.2f}, "
            f"TOTAL: €{b.total_cost_eur or 0:.2f}\n"
            f"Gas commodity price: €{energy_unit_price if energy_unit_price is not None else 0:.4f}/Smc\n"
        )

    if validation:
        context_parts.append(f"Bill analysis:\n{validation}\n")

    if market:
        context_parts.append(f"Market research:\n{market}\n")

    no_better_offer_markers = [
        "no verifiable better offer was found",
        "no better offers were found",
    ]
    market_lower = market.lower() if isinstance(market, str) else ""
    no_better_offers = any(marker in market_lower for marker in no_better_offer_markers)

    user_msg = (
        "\n".join(context_parts)
        + "\n\nGenerate the complete final Markdown report with recommendations "
        "for the client. Include comparison tables and concrete savings estimates only when based "
        "on real, verifiable offers. If market research contains no verifiable better offer, "
        "state this explicitly and do not suggest example offers."
    )

    if not bills and requirements:
        user_msg += (
            "\n\nNEW SUPPLY MODE: there is no existing bill or current situation. "
            "Generate the report using estimated consumption and compare only real offers found. "
            "Do not create bill breakdown sections or savings against past usage. "
            f"Declared requirements: {requirements.model_dump(mode='json')}."
        )

    if no_better_offers:
        user_msg += (
            "\n\nADDITIONAL CONSTRAINT: there are no verifiable better offers. "
            "In the 'Alternative offers' section, include only a short message "
            "stating this, without tables or offer lists."
        )

    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.1,
    )
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), {"role": "user", "content": user_msg}])

    return {
        "messages": [{"role": "assistant", "content": response.content}],
        "final_report": response.content,
    }
