"""Tools for searching electricity and gas offers on the web using Tavily."""

from langchain_core.tools import tool

from agent_bill.config import TAVILY_API_KEY


@tool
def search_energy_offers(query: str) -> str:
    """Search for electricity and gas offers on the Italian market using Tavily.

    Args:
        query: Search query (e.g. 'best Italian free-market electricity offers 2026')

    Returns:
        Search results as text.
    """
    from tavily import TavilyClient

    if not TAVILY_API_KEY:
        return "Error: TAVILY_API_KEY is not configured. Update the .env file."

    client = TavilyClient(api_key=TAVILY_API_KEY)
    response = client.search(
        query=query,
        search_depth="basic",
        max_results=5,
        include_answer=True,
        include_domains=["segugio.it", "facile.it", "selectra.net", "luce-gas.it",
                         "confronta.it", "prontobolletta.it", "arera.it"],
    )

    results = []
    if response.get("answer"):
        results.append(f"Summary: {response['answer']}\n")

    for r in response.get("results", []):
        results.append(f"- {r['title']}\n  {r['url']}\n  {r.get('content', '')[:300]}\n")

    return "\n".join(results) if results else "No results found."


@tool
def search_energy_prices(utility_type: str) -> str:
    """Search for current electricity or gas prices on the Italian market.

    Args:
        utility_type: 'electricity' or 'gas'

    Returns:
        Current pricing information.
    """
    from tavily import TavilyClient

    if not TAVILY_API_KEY:
        return "Error: TAVILY_API_KEY is not configured."

    queries = {
        "electricity": "average electricity price per kWh Italy free market 2026",
        "gas": "average natural gas price per Smc Italy free market 2026",
    }
    query = queries.get(utility_type, queries["electricity"])

    client = TavilyClient(api_key=TAVILY_API_KEY)
    response = client.search(query=query, search_depth="basic", max_results=3, include_answer=True)

    results = []
    if response.get("answer"):
        results.append(f"Summary: {response['answer']}\n")

    for r in response.get("results", []):
        results.append(f"- {r['title']}: {r.get('content', '')[:200]}\n")

    return "\n".join(results) if results else "No results found."
