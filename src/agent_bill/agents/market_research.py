"""MarketResearchAgent: search for electricity and gas offers using Tavily."""

from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama

from agent_bill.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from agent_bill.graph.state import AgentState
from agent_bill.models.bill import UtilityType
from agent_bill.tools.web_search import search_energy_offers, search_energy_prices

SYSTEM_PROMPT = """You are an expert on the Italian energy market.
Analyze web search results for electricity and gas offers
and identify the best available offers for the client's profile.

IMPORTANT: Compare providers ONLY on the energy commodity price (€/kWh or €/Smc),
because the other bill items (transport, system charges, taxes) are regulated by ARERA
and remain identical across providers.

Use this terminology consistently:
- "Energy commodity price" = unit price of the energy component alone
- "All-inclusive total unit cost" = total bill cost / consumption
- Do not call the all-inclusive cost an "average price".

For each offer you identify, extract and report:
- Provider name
- Offer name
- Energy commodity price per kWh or Smc
- Monthly fixed cost (if any)
- Offer page URL (ESSENTIAL: always include the link)
- Any promotions, restrictions or contract duration

Reliability constraints:
- Report ONLY offers actually present in the supplied web results.
- NEVER invent providers, offer names, prices or URLs.
- Exclude offers without at least a provider, a price and a verifiable URL in the results.
- If you find no real offer better than the current situation, explicitly write:
    "No verifiable better offer was found in the analyzed web results."
- Do not use placeholders such as "Provider A", "Offer 1", "#" or fictional URLs.

To calculate savings:
1. Take the offer's price per kWh (or Smc)
2. Multiply it by the client's consumption
3. Add the unchanged fixed costs (network, system charges, taxes) from the current bill
4. Compare with the current total cost

For a NEW SUPPLY without bills:
- there is no current price or provider to beat
- compare real offers using estimated consumption
- estimate the energy commodity cost and any fixed costs stated in the offer
- do not invent transport costs, system charges, taxes or savings against a previous situation

Respond in English. Be precise with numbers."""


def market_research_node(state: AgentState) -> dict:
    """Graph node: research market offers and compare them with current offers."""
    profile = state.get("consumption_profile")
    bills = state.get("bills", [])
    requirements = state.get("new_supply_requirements")

    if not profile or (not bills and not requirements):
        return {
            "messages": [{"role": "assistant", "content": "Insufficient data for market research."}],
            "market_research": "No consumption data available.",
        }

    providers = set()
    has_electricity = bool(requirements and UtilityType.ELECTRICITY in requirements.utility_types)
    has_gas = bool(requirements and UtilityType.GAS in requirements.utility_types)
    for bill in bills:
        providers.add(bill.provider)
        if bill.utility_type == UtilityType.ELECTRICITY:
            has_electricity = True
        else:
            has_gas = True

    search_results = []

    if has_electricity:
        query_e = (
            f"best electricity offers Italian free energy market current year "
            f"consumption {profile.avg_monthly_kwh or 150} kWh per month price per kWh"
        )
        results_e = search_energy_offers.invoke({"query": query_e})
        prices_e = search_energy_prices.invoke({"utility_type": "electricity"})
        search_results.append(f"=== ELECTRICITY OFFERS ===\n{results_e}\n\nCurrent prices:\n{prices_e}")

    if has_gas:
        query_g = (
            f"best natural gas offers Italian free energy market current year "
            f"consumption {profile.avg_monthly_smc or 80} Smc per month price per Smc"
        )
        results_g = search_energy_offers.invoke({"query": query_g})
        prices_g = search_energy_prices.invoke({"utility_type": "gas"})
        search_results.append(f"=== GAS OFFERS ===\n{results_g}\n\nCurrent prices:\n{prices_g}")

    elec_bills = [b for b in bills if b.utility_type == UtilityType.ELECTRICITY]
    gas_bills = [b for b in bills if b.utility_type == UtilityType.GAS]

    cost_breakdown = ""
    if elec_bills:
        avg_energy_price = None
        energy_prices = [b.energy_price_per_unit for b in elec_bills if b.energy_price_per_unit]
        if energy_prices:
            avg_energy_price = sum(energy_prices) / len(energy_prices)

        avg_energy_cost = sum(b.energy_cost_eur or 0 for b in elec_bills) / len(elec_bills)
        avg_transport = sum(b.transport_cost_eur or 0 for b in elec_bills) / len(elec_bills)
        avg_system = sum(b.system_charges_eur or 0 for b in elec_bills) / len(elec_bills)
        avg_taxes = sum(b.taxes_eur or 0 for b in elec_bills) / len(elec_bills)

        cost_breakdown += (
            f"\nAverage ELECTRICITY cost breakdown (monthly):\n"
            f"  - Energy commodity: €{avg_energy_cost:.2f}"
        )
        if avg_energy_price:
            cost_breakdown += f" (unit price: €{avg_energy_price:.4f}/kWh)"
        cost_breakdown += (
            f"\n  - Transport and meter management: €{avg_transport:.2f}"
            f"\n  - System charges: €{avg_system:.2f}"
            f"\n  - Taxes: €{avg_taxes:.2f}"
            f"\n  - Fixed costs (unchanged across providers): €{avg_transport + avg_system + avg_taxes:.2f}\n"
        )

    if gas_bills:
        avg_energy_price_g = None
        energy_prices_g = [b.energy_price_per_unit for b in gas_bills if b.energy_price_per_unit]
        if energy_prices_g:
            avg_energy_price_g = sum(energy_prices_g) / len(energy_prices_g)

        avg_energy_cost_g = sum(b.energy_cost_eur or 0 for b in gas_bills) / len(gas_bills)
        avg_transport_g = sum(b.transport_cost_eur or 0 for b in gas_bills) / len(gas_bills)
        avg_system_g = sum(b.system_charges_eur or 0 for b in gas_bills) / len(gas_bills)
        avg_taxes_g = sum(b.taxes_eur or 0 for b in gas_bills) / len(gas_bills)

        cost_breakdown += (
            f"\nAverage GAS cost breakdown (monthly):\n"
            f"  - Gas commodity: €{avg_energy_cost_g:.2f}"
        )
        if avg_energy_price_g:
            cost_breakdown += f" (unit price: €{avg_energy_price_g:.4f}/Smc)"
        cost_breakdown += (
            f"\n  - Transport and meter management: €{avg_transport_g:.2f}"
            f"\n  - System charges: €{avg_system_g:.2f}"
            f"\n  - Taxes: €{avg_taxes_g:.2f}"
            f"\n  - Fixed costs (unchanged across providers): €{avg_transport_g + avg_system_g + avg_taxes_g:.2f}\n"
        )

    situation_label = "New supply: estimated profile" if not bills else "Client's current situation"
    provider_label = ", ".join(providers) if providers else "no current provider"
    current_info = (
        f"{situation_label}:\n"
        f"- Providers: {provider_label}\n"
        f"- Average monthly electricity consumption: {profile.avg_monthly_kwh or 'N/A'} kWh\n"
        f"- Average monthly gas consumption: {profile.avg_monthly_smc or 'N/A'} Smc\n"
        f"- Average monthly electricity cost: €{profile.avg_monthly_cost_electricity or 'N/A'}\n"
        f"- Average monthly gas cost: €{profile.avg_monthly_cost_gas or 'N/A'}\n"
        f"- Estimated total annual cost: €{profile.total_annual_cost or 'N/A'}\n"
        f"{cost_breakdown}"
    )

    user_msg = (
        f"{current_info}\n\nOffer search results:\n\n"
        + "\n\n".join(search_results)
        + "\n\nAnalyze the offers found. "
        + ("Compare them using the estimated consumption profile. " if not bills else "Compare them with the client's current situation. ")
        + "Identify the best opportunities. If results contain no real offers "
        + "with verifiable prices and URLs, "
        + ("" if not bills else "or none beats the current energy commodity price, ")
        + "state this explicitly without inventing alternatives."
    )

    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), {"role": "user", "content": user_msg}])

    return {
        "messages": [{"role": "assistant", "content": response.content}],
        "market_research": response.content,
    }
