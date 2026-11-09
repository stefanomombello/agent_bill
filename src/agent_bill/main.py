"""CLI entry point for Agent Bill."""

from datetime import date
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, FloatPrompt, IntPrompt, Confirm
from rich.table import Table

from agent_bill.config import OUTPUT_DIR
from agent_bill.models.analysis import AnalysisMode, EnergySource, NewSupplyRequirements
from agent_bill.models.bill import BillData, UtilityType
from agent_bill.models.cadastral import CadastralInfo
from agent_bill.tools.cadastral_registry import (
    build_property_id,
    cadastral_info_from_record,
    list_client_properties,
    normalize_tax_code,
    upsert_property_record,
)
from agent_bill.tools.pdf_extractor import parse_bill_from_pdf
from agent_bill.tools.energy_calc import estimate_new_supply_profile
from agent_bill.graph.workflow import build_workflow

console = Console()


def collect_client_identity() -> tuple[str, str]:
    """Collect the client's basic identification details."""
    console.print("\n[bold cyan]--- Client Details ---[/bold cyan]")
    client_name = Prompt.ask("Client's full name").strip()
    tax_code = normalize_tax_code(Prompt.ask("Client's Italian tax code").strip())
    return client_name, tax_code


def collect_analysis_mode() -> AnalysisMode:
    """Select the type of analysis to run."""
    console.print("\n[bold cyan]--- Analysis Type ---[/bold cyan]")
    choice = Prompt.ask(
        "What would you like to analyze?",
        choices=["bill", "new-supply"],
        default="bill",
    )
    return AnalysisMode.NEW_SUPPLY if choice == "new-supply" else AnalysisMode.BILL_COMPARISON


def _prompt_energy_source(label: str) -> EnergySource:
    source = Prompt.ask(
        label,
        choices=["gas", "heat-pump", "electricity", "centralized", "other"],
        default="other",
    )
    return {
        "gas": EnergySource.GAS,
        "heat-pump": EnergySource.HEAT_PUMP,
        "electricity": EnergySource.ELECTRICITY,
        "centralized": EnergySource.CENTRALIZED,
        "other": EnergySource.OTHER,
    }[source]


def collect_new_supply_requirements() -> NewSupplyRequirements:
    """Collect usage requirements for estimating a new supply."""
    console.print("\n[bold cyan]--- New Supply Requirements ---[/bold cyan]")
    utility_choice = Prompt.ask(
        "Utilities to activate",
        choices=["electricity", "gas", "electricity-gas"],
        default="electricity-gas",
    )
    utility_types = []
    if utility_choice in {"electricity", "electricity-gas"}:
        utility_types.append(UtilityType.ELECTRICITY)
    if utility_choice in {"gas", "electricity-gas"}:
        utility_types.append(UtilityType.GAS)

    heating_source = _prompt_energy_source("Planned heating source")
    hot_water_source = _prompt_energy_source("Planned hot water source")
    gas_for_cooking = (
        Confirm.ask("Will gas also be used for cooking?", default=False)
        if UtilityType.GAS in utility_types
        else False
    )

    estimated_annual_kwh = None
    if UtilityType.ELECTRICITY in utility_types and Confirm.ask(
        "Do you already know the expected annual electricity consumption?", default=False
    ):
        estimated_annual_kwh = FloatPrompt.ask("Expected annual electricity consumption (kWh)")

    estimated_annual_smc = None
    if UtilityType.GAS in utility_types and Confirm.ask(
        "Do you already know the expected annual gas consumption?", default=False
    ):
        estimated_annual_smc = FloatPrompt.ask("Expected annual gas consumption (Smc)")

    notes = Prompt.ask("Other requirements or constraints (optional)", default="").strip()
    return NewSupplyRequirements(
        utility_types=utility_types,
        heating_source=heating_source,
        hot_water_source=hot_water_source,
        gas_for_cooking=gas_for_cooking,
        estimated_annual_kwh=estimated_annual_kwh,
        estimated_annual_smc=estimated_annual_smc,
        notes=notes,
    )


def collect_bills_from_pdf() -> list[BillData]:
    """Load bills from PDF files."""
    bills = []

    while True:
        console.print("\n[bold cyan]--- Load PDF Bill ---[/bold cyan]")
        pdf_path = Prompt.ask("Path to the PDF bill")
        pdf_path = pdf_path.strip().strip('"').strip("'")

        if not Path(pdf_path).exists():
            console.print(f"[bold red]File not found:[/bold red] {pdf_path}")
            continue

        try:
            with console.status("[bold green]Extracting data from the PDF..."):
                bill = parse_bill_from_pdf(pdf_path)

            consumption = (
                f"{bill.consumption_kwh} kWh"
                if bill.consumption_kwh
                else f"{bill.consumption_smc} Smc"
            )
            unit_price = (
                f"€{bill.energy_price_per_unit}/{'kWh' if bill.consumption_kwh else 'Smc'}"
                if bill.energy_price_per_unit
                else "N/A"
            )
            console.print(Panel(
                f"Type: {'Electricity' if bill.utility_type == UtilityType.ELECTRICITY else 'Gas'}\n"
                f"Provider: {bill.provider}\n"
                f"Period: {bill.period_start} / {bill.period_end}\n"
                f"Consumption: {consumption}\n"
                f"Total cost: €{bill.total_cost_eur:.2f}\n"
                f"  ├─ Energy commodity: €{bill.energy_cost_eur or 'N/A'} ({unit_price})\n"
                f"  ├─ Transport/network: €{bill.transport_cost_eur or 'N/A'}\n"
                f"  ├─ System charges: €{bill.system_charges_eur or 'N/A'}\n"
                f"  └─ Taxes: €{bill.taxes_eur or 'N/A'}\n"
                f"POD/PDR: {bill.pod_pdr or 'N/A'}",
                title="Extracted Data",
                border_style="cyan",
            ))

            if Confirm.ask("Is the extracted data correct?", default=True):
                bills.append(bill)
                console.print("[green]Bill added.[/green]")
            else:
                console.print("[yellow]Bill discarded.[/yellow]")

        except Exception as e:
            console.print(f"[bold red]Error processing the PDF:[/bold red] {e}")

        if not Confirm.ask("Would you like to load another bill?", default=False):
            break

    return bills


def prompt_cadastral_data() -> CadastralInfo:
    """Collect property details from the user."""
    console.print("\n[bold cyan]--- Property Details ---[/bold cyan]")

    cadastral_info = CadastralInfo(
        address=Prompt.ask("Full address"),
        city=Prompt.ask("Municipality"),
        province=Prompt.ask("Province (code, e.g. MI)"),
        property_type=Prompt.ask(
            "Property type", choices=["apartment", "villa", "office", "other"],
            default="apartment"
        ),
        surface_sqm=FloatPrompt.ask("Floor area (sqm)"),
        energy_class=Prompt.ask("Energy rating (A1-G, leave blank if unknown)", default=""),
        residents=IntPrompt.ask("Number of residents/occupants", default=2),
        heating_type=Prompt.ask(
            "Heating type", choices=["individual", "centralized"], default="individual"
        ),
        year_built=IntPrompt.ask("Year built (0 if unknown)", default=0) or None,
    )
    cadastral_info.property_id = build_property_id(
        cadastral_info.address,
        cadastral_info.city,
        cadastral_info.province,
    )
    return cadastral_info


def collect_cadastral(client_name: str, tax_code: str) -> CadastralInfo | None:
    """Retrieve property details from the registry or collect them manually."""
    existing_properties = list_client_properties(tax_code)

    if existing_properties:
        console.print("\n[bold cyan]--- Registered Properties ---[/bold cyan]")
        table = Table(title="Client Property History")
        table.add_column("#", style="cyan")
        table.add_column("Identifier")
        table.add_column("Property")

        for index, property_record in enumerate(existing_properties, start=1):
            table.add_row(
                str(index),
                property_record["property_id"],
                property_record["display_name"],
            )

        table.add_row("0", "new", "Add a new property")
        console.print(table)

        choice = IntPrompt.ask("Select the property to use", default=1)
        if choice != 0 and 1 <= choice <= len(existing_properties):
            selected = existing_properties[choice - 1]
            console.print(
                f"[green]Using saved property details for:[/green] {selected['display_name']}"
            )
            return cadastral_info_from_record(selected, selected["property_id"])

    if not Confirm.ask("\nWould you like to enter property details?", default=True):
        return None

    cadastral_info = prompt_cadastral_data()
    property_id = upsert_property_record(client_name, tax_code, cadastral_info)
    cadastral_info.property_id = property_id
    console.print(
        f"[green]Property details saved to the registry.[/green] Property ID: {property_id}"
    )
    return cadastral_info


def display_summary(
    bills: list[BillData],
    cadastral: CadastralInfo | None,
    new_supply: NewSupplyRequirements | None = None,
):
    """Display a summary of the supplied data."""
    table = Table(title="Loaded Bills")
    table.add_column("Type", style="cyan")
    table.add_column("Provider")
    table.add_column("Period")
    table.add_column("Consumption")
    table.add_column("Cost", style="green")

    for bill in bills:
        consumption = (
            f"{bill.consumption_kwh} kWh"
            if bill.consumption_kwh
            else f"{bill.consumption_smc} Smc"
        )
        table.add_row(
            "Electricity" if bill.utility_type == UtilityType.ELECTRICITY else "Gas",
            bill.provider,
            f"{bill.period_start} / {bill.period_end}",
            consumption,
            f"€{bill.total_cost_eur:.2f}",
        )

    if bills:
        console.print(table)

    if cadastral:
        console.print(Panel(
            f"Property ID: {cadastral.property_id or 'N/A'}\n"
            f"{cadastral.property_type} - {cadastral.surface_sqm} sqm - "
            f"{cadastral.address} - "
            f"{cadastral.city} ({cadastral.province}) - "
            f"{cadastral.residents} residents - "
            f"Heating: {cadastral.heating_type}",
            title="Property Details",
        ))

    if new_supply and cadastral:
        profile = estimate_new_supply_profile(cadastral, new_supply)
        utilities = ", ".join(item.value for item in new_supply.utility_types)
        console.print(Panel(
            f"Requested utilities: {utilities}\n"
            f"Estimated electricity consumption: {profile.avg_monthly_kwh or 'N/A'} kWh/month\n"
            f"Estimated gas consumption: {profile.avg_monthly_smc or 'N/A'} Smc/month\n"
            f"Heating source: {new_supply.heating_source.value}\n"
            f"Hot water source: {new_supply.hot_water_source.value}\n"
            "Consumption figures are indicative estimates and will be labeled as such in the report.",
            title="New Supply Profile",
            border_style="yellow",
        ))


def save_report(report: str, client_name: str):
    """Save the final report to a Markdown file."""
    filename = f"report_{client_name.lower().replace(' ', '_')}_{date.today().isoformat()}.md"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(report, encoding="utf-8")
    console.print(f"\n[bold green]Report saved to:[/bold green] {filepath}")


def main():
    """Main entry point."""
    console.print(Panel.fit(
        "[bold]Agent Bill[/bold] - Utility Bill Analysis and Energy Advice",
        border_style="blue",
    ))

    client_name, tax_code = collect_client_identity()
    analysis_mode = collect_analysis_mode()

    bills = []
    if analysis_mode == AnalysisMode.BILL_COMPARISON:
        console.print("\n[bold]Load the client's bills as PDF files.[/bold]")
        bills = collect_bills_from_pdf()
        if not bills:
            console.print("[bold red]No bills loaded. Exiting.[/bold red]")
            return

    cadastral = collect_cadastral(client_name, tax_code)
    new_supply = None
    if analysis_mode == AnalysisMode.NEW_SUPPLY:
        if not cadastral:
            console.print("[bold red]Property details are required for estimation.[/bold red]")
            return
        new_supply = collect_new_supply_requirements()

    display_summary(bills, cadastral, new_supply)

    if not Confirm.ask("\nIs the data correct? Proceed with the analysis?", default=True):
        console.print("[yellow]Operation canceled.[/yellow]")
        return

    console.print("\n[bold]Starting analysis...[/bold]\n")

    app = build_workflow()

    with console.status("[bold green]Analysis in progress..."):
        result = app.invoke({
            "client_name": client_name,
            "analysis_mode": analysis_mode,
            "bills": bills,
            "cadastral_info": cadastral,
            "new_supply_requirements": new_supply,
            "messages": [],
        })

    # Output
    report = result.get("final_report", "No report generated.")
    console.print("\n")
    console.print(Panel(report, title="Final Report", border_style="green"))

    if Confirm.ask("\nWould you like to save the report?", default=True):
        save_report(report, client_name)

    console.print("\n[bold blue]Thank you for using Agent Bill![/bold blue]")


if __name__ == "__main__":
    main()
