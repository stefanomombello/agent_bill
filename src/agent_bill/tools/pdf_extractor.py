"""Tools for extracting utility bill data from PDF files."""

import json
from pathlib import Path

import fitz  # PyMuPDF
from langchain_core.messages import SystemMessage
from langchain_ollama import ChatOllama

from agent_bill.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from agent_bill.models.bill import BillData

EXTRACTION_PROMPT = """You are an expert on Italian energy bills (electricity and gas).
You are given text extracted from a PDF bill. Extract the data and return it
ONLY as valid JSON, with no additional text before or after it.

Use this JSON structure:
{
    "utility_type": "electricity" or "gas",
    "provider": "provider name",
    "contract_type": "free market" or "regulated tariff",
    "period_start": "YYYY-MM-DD",
    "period_end": "YYYY-MM-DD",
        "consumption_kwh": number or null (electricity only),
        "consumption_smc": number or null (gas only),
        "total_cost_eur": number (total bill amount),
        "energy_cost_eur": number or null (energy commodity cost only),
        "energy_price_per_unit": number or null (energy commodity unit price in €/kWh or €/Smc),
        "transport_cost_eur": number or null (transport and meter management / network costs),
        "system_charges_eur": number or null (system charges),
        "taxes_eur": number or null (taxes: excise duty + VAT),
        "pod_pdr": "POD or PDR code",
        "power_kw": number or null (electricity only)
}

Rules:
- Identify electricity or gas bills from their contents
- Costs must be decimal numbers in EUR (e.g. 65.43)
- Dates must use YYYY-MM-DD format
- Use null for missing data
- POD starts with "IT" and identifies electricity supplies; PDR identifies gas supplies
- IMPORTANT: extract ALL cost items separately:
    * energy_cost_eur = energy commodity cost
    * energy_price_per_unit = unit price per kWh or Smc (if stated on the bill)
    * transport_cost_eur = transport and meter management / distribution costs
    * system_charges_eur = system charges
    * taxes_eur = total taxes (excise duty + VAT)
- If explicit unit rates are present (e.g. a €/kWh or €/Smc price table),
        ALWAYS prioritize them for energy_price_per_unit.
- If energy_price_per_unit is not explicitly stated, calculate it as a fallback:
    energy_cost_eur / consumption_kwh (or consumption_smc)
- Return descriptive values in English, preserving provider names and supply identifiers
- Respond ONLY with JSON, no other text"""


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from a PDF file."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"The file is not a PDF: {pdf_path}")

    doc = fitz.open(str(path))
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()

    return "\n".join(text_parts)


def parse_bill_from_pdf(pdf_path: str) -> BillData:
    """Extract structured bill data from a PDF file using the LLM."""
    raw_text = extract_text_from_pdf(pdf_path)

    if not raw_text.strip():
        raise ValueError(
            f"The PDF '{pdf_path}' contains no extractable text. "
            "It may be a scanned (image-only) PDF."
        )

    # Preserve both ends: explicit unit rates often appear in the final sections.
    max_chars = 30000
    if len(raw_text) > max_chars:
        half = max_chars // 2
        raw_text = (
            raw_text[:half]
            + "\n\n[... MIDDLE CONTENT TRUNCATED ...]\n\n"
            + raw_text[-half:]
        )

    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )
    response = llm.invoke([
        SystemMessage(content=EXTRACTION_PROMPT),
        {"role": "user", "content": f"Here is the bill text:\n\n{raw_text}"},
    ])

    content = response.content.strip()

    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"The LLM did not produce valid JSON. Response:\n{content}\nError: {e}"
        )

    return BillData(**data)
