"""Tests for the energy calculation module."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent_bill import main as cli
from agent_bill.agents import advisor
from agent_bill.agents.bill_validator import bill_validator_node
from agent_bill.models.analysis import AnalysisMode, EnergySource, NewSupplyRequirements
from agent_bill.models.bill import BillData, UtilityType
from agent_bill.models.cadastral import CadastralInfo
from agent_bill.tools.energy_calc import (
    build_consumption_profile,
    estimate_annual_saving,
    estimate_new_supply_profile,
)


def build_cadastral() -> CadastralInfo:
    return CadastralInfo(
        address="Example Street 1",
        city="Milan",
        province="MI",
        surface_sqm=100,
        energy_class="C",
        residents=2,
    )


def test_build_consumption_profile_electricity():
    bills = [
        BillData(
            utility_type=UtilityType.ELECTRICITY,
            provider="Enel",
            period_start="2026-01-01",
            period_end="2026-01-31",
            consumption_kwh=200,
            total_cost_eur=60.0,
        ),
        BillData(
            utility_type=UtilityType.ELECTRICITY,
            provider="Enel",
            period_start="2026-02-01",
            period_end="2026-02-28",
            consumption_kwh=180,
            total_cost_eur=55.0,
        ),
    ]
    profile = build_consumption_profile(bills)
    assert profile.avg_monthly_kwh == 190.0
    assert profile.avg_monthly_cost_electricity == 57.5
    assert profile.total_annual_cost == 690.0


def test_build_consumption_profile_gas():
    bills = [
        BillData(
            utility_type=UtilityType.GAS,
            provider="Eni",
            period_start="2026-01-01",
            period_end="2026-01-31",
            consumption_smc=100,
            total_cost_eur=120.0,
        ),
    ]
    profile = build_consumption_profile(bills)
    assert profile.avg_monthly_smc == 100.0
    assert profile.avg_monthly_cost_gas == 120.0


def test_build_consumption_profile_mixed():
    bills = [
        BillData(
            utility_type=UtilityType.ELECTRICITY,
            provider="Enel",
            period_start="2026-01-01",
            period_end="2026-01-31",
            consumption_kwh=200,
            total_cost_eur=60.0,
        ),
        BillData(
            utility_type=UtilityType.GAS,
            provider="Eni",
            period_start="2026-01-01",
            period_end="2026-01-31",
            consumption_smc=80,
            total_cost_eur=100.0,
        ),
    ]
    profile = build_consumption_profile(bills)
    assert profile.avg_monthly_kwh == 200.0
    assert profile.avg_monthly_smc == 80.0
    assert profile.total_annual_cost == 1920.0  # (60*12) + (100*12)


def test_estimate_annual_saving():
    saving = estimate_annual_saving(
        current_annual_cost=720.0,
        new_price_per_unit=0.20,
        annual_consumption=2400,
        new_fixed_monthly=5.0,
    )
    # 720 - (0.20*2400 + 5*12) = 720 - (480+60) = 180
    assert saving == 180.0


def test_cost_per_unit():
    bill = BillData(
        utility_type=UtilityType.ELECTRICITY,
        provider="Enel",
        period_start="2026-01-01",
        period_end="2026-01-31",
        consumption_kwh=200,
        total_cost_eur=60.0,
    )
    assert bill.cost_per_unit == 0.3


def test_estimate_new_supply_profile_with_gas_heating():
    requirements = NewSupplyRequirements(
        utility_types=[UtilityType.ELECTRICITY, UtilityType.GAS],
        heating_source=EnergySource.GAS,
        hot_water_source=EnergySource.GAS,
        gas_for_cooking=True,
    )

    profile = estimate_new_supply_profile(build_cadastral(), requirements)

    assert profile.is_estimated is True
    assert profile.avg_monthly_kwh == 166.7
    assert profile.avg_monthly_smc == 72.0
    assert profile.total_annual_cost is None


def test_estimate_new_supply_profile_with_heat_pump():
    requirements = NewSupplyRequirements(
        utility_types=[UtilityType.ELECTRICITY],
        heating_source=EnergySource.HEAT_PUMP,
        hot_water_source=EnergySource.HEAT_PUMP,
    )

    profile = estimate_new_supply_profile(build_cadastral(), requirements)

    assert profile.avg_monthly_kwh == 444.4
    assert profile.avg_monthly_smc is None


def test_validator_builds_profile_without_bills():
    requirements = NewSupplyRequirements(
        utility_types=[UtilityType.ELECTRICITY],
        estimated_annual_kwh=2400,
    )

    result = bill_validator_node({
        "bills": [],
        "cadastral_info": build_cadastral(),
        "new_supply_requirements": requirements,
    })

    assert result["consumption_profile"].avg_monthly_kwh == 200.0
    assert result["consumption_profile"].is_estimated is True
    assert "New supply without historical data" in result["validation_notes"]


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("bill", AnalysisMode.BILL_COMPARISON), ("new-supply", AnalysisMode.NEW_SUPPLY)],
)
def test_english_analysis_mode_choices(monkeypatch, choice, expected):
    prompt = Mock(return_value=choice)
    monkeypatch.setattr(cli.Prompt, "ask", prompt)

    assert cli.collect_analysis_mode() == expected
    assert prompt.call_args.kwargs["choices"] == ["bill", "new-supply"]


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("gas", EnergySource.GAS),
        ("heat-pump", EnergySource.HEAT_PUMP),
        ("electricity", EnergySource.ELECTRICITY),
        ("centralized", EnergySource.CENTRALIZED),
        ("other", EnergySource.OTHER),
    ],
)
def test_english_energy_source_choices(monkeypatch, choice, expected):
    prompt = Mock(return_value=choice)
    monkeypatch.setattr(cli.Prompt, "ask", prompt)

    assert cli._prompt_energy_source("Heating source") == expected
    assert choice in prompt.call_args.kwargs["choices"]


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("electricity", [UtilityType.ELECTRICITY]),
        ("gas", [UtilityType.GAS]),
        ("electricity-gas", [UtilityType.ELECTRICITY, UtilityType.GAS]),
    ],
)
def test_english_utility_choices(monkeypatch, choice, expected):
    monkeypatch.setattr(cli.Prompt, "ask", Mock(side_effect=[choice, ""]))
    monkeypatch.setattr(cli.Confirm, "ask", Mock(return_value=False))
    monkeypatch.setattr(cli, "_prompt_energy_source", Mock(return_value=EnergySource.OTHER))

    assert cli.collect_new_supply_requirements().utility_types == expected


def test_advisor_recognizes_english_no_better_offer_message(monkeypatch):
    llm = Mock()
    llm.invoke.return_value = SimpleNamespace(content="English report")
    monkeypatch.setattr(advisor, "ChatOllama", Mock(return_value=llm))

    result = advisor.advisor_node({
        "market_research": "No verifiable better offer was found in the analyzed web results.",
    })

    messages = llm.invoke.call_args.args[0]
    assert "Respond in English" in messages[0].content
    assert "ADDITIONAL CONSTRAINT" in messages[1]["content"]
    assert "without tables or offer lists" in messages[1]["content"]
    assert result["final_report"] == "English report"
