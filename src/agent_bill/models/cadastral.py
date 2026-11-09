from pydantic import BaseModel, Field


class CadastralInfo(BaseModel):
    """Cadastral details for the client's property."""

    property_id: str | None = Field(
        default=None,
        description="Property identifier for the local registry",
    )

    address: str = Field(description="Full address")
    city: str = Field(description="Municipality")
    province: str = Field(description="Province code")
    property_type: str = Field(
        default="apartment",
        description="Property type (apartment, villa, office, etc.)",
    )
    surface_sqm: float = Field(description="Floor area in square meters")
    energy_class: str = Field(
        default="", description="Energy rating (A1-G, if known)"
    )
    residents: int = Field(default=1, description="Number of residents/occupants")
    heating_type: str = Field(
        default="individual",
        description="Heating type (individual, centralized)",
    )
    year_built: int | None = Field(
        default=None, description="Year built"
    )
