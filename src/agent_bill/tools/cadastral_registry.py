"""Local persistence of cadastral records by client and property."""

import json
import re
import unicodedata
from pathlib import Path

from agent_bill.config import DATA_DIR
from agent_bill.models.cadastral import CadastralInfo


REGISTRY_PATH = DATA_DIR / "cadastral_registry.json"


def normalize_tax_code(tax_code: str) -> str:
    """Normalize the Italian tax code for lookups."""
    return re.sub(r"\s+", "", tax_code).upper()


def normalize_text(value: str) -> str:
    """Normalize free text to build stable keys."""
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def build_property_id(address: str, city: str, province: str) -> str:
    """Build a stable, readable property identifier.

    Use the full address, municipality and province already collected by the app,
    without requiring additional technical identifiers.
    """
    parts = [normalize_text(address), normalize_text(city), normalize_text(province)]
    return "__".join(part for part in parts if part)


def _ensure_registry_file() -> None:
    REGISTRY_PATH.parent.mkdir(exist_ok=True)
    if not REGISTRY_PATH.exists():
        REGISTRY_PATH.write_text('{"clients": {}}', encoding="utf-8")


def load_registry() -> dict:
    """Load the local registry, creating it if missing."""
    _ensure_registry_file()
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict) -> None:
    """Save the local registry as JSON."""
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_client_properties(tax_code: str) -> list[dict]:
    """Return the properties registered for a client."""
    registry = load_registry()
    client = registry.get("clients", {}).get(normalize_tax_code(tax_code), {})
    properties = client.get("properties", {})
    records = []
    for property_id, record in properties.items():
        records.append({"property_id": property_id, **record})
    return records


def get_property_record(tax_code: str, property_id: str) -> dict | None:
    """Retrieve a specific property from the registry."""
    registry = load_registry()
    client = registry.get("clients", {}).get(normalize_tax_code(tax_code), {})
    return client.get("properties", {}).get(property_id)


def cadastral_info_from_record(record: dict, property_id: str) -> CadastralInfo:
    """Convert a registry record to CadastralInfo."""
    return CadastralInfo(property_id=property_id, **record["cadastral_info"])


def upsert_property_record(
    client_name: str,
    tax_code: str,
    cadastral_info: CadastralInfo,
) -> str:
    """Insert or update a client's cadastral details for a specific property."""
    registry = load_registry()
    normalized_tax_code = normalize_tax_code(tax_code)
    property_id = cadastral_info.property_id or build_property_id(
        cadastral_info.address,
        cadastral_info.city,
        cadastral_info.province,
    )

    client_bucket = registry.setdefault("clients", {}).setdefault(
        normalized_tax_code,
        {"client_name": client_name, "tax_code": normalized_tax_code, "properties": {}},
    )
    client_bucket["client_name"] = client_name
    client_bucket["tax_code"] = normalized_tax_code
    client_bucket.setdefault("properties", {})[property_id] = {
        "display_name": f"{cadastral_info.address}, {cadastral_info.city} ({cadastral_info.province})",
        "cadastral_info": cadastral_info.model_dump(exclude={"property_id"}),
    }

    save_registry(registry)
    return property_id