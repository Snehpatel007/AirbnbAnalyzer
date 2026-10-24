import pytest
from src.agent.analyzer import MarketAnalysisAgent
from src.models.database import SessionLocal


def test_agent_answers():
    db = SessionLocal()
    agent = MarketAnalysisAgent(db)

    # 1. Compare Bopal vs Shilaj
    res1 = agent.answer_query("Compare Bopal vs Shilaj")
    assert "Shilaj" in res1["answer"]
    assert "Bopal" in res1["answer"]
    assert "ADR" in res1["answer"]
    assert "RevPAR" in res1["answer"]

    # 2. Highest ADR
    res2 = agent.answer_query("Which area has the highest ADR?")
    assert "highest Average Daily Rate" in res2["answer"] or "ADR" in res2["answer"]

    # 3. Best RevPAR combination
    res3 = agent.answer_query("Which areas currently have the best combination of observed occupancy, ADR and RevPAR?")
    assert "Observed RevPAR Proxy" in res3["answer"]

    # 4. Improved the most in last 30 days
    res4 = agent.answer_query("Which area has improved the most in the last 30 days?")
    assert "percentage points" in res4["answer"]

    # 5. Increasing demand but decreasing supply
    res5 = agent.answer_query("Which area has increasing demand but decreasing supply?")
    assert "supply" in res5["answer"].lower()

    # 6. Specific Area: Ghuma
    res6 = agent.answer_query("Show me Ghuma's last 30 days.")
    assert "Ghuma" in res6["answer"]
    assert "Lease Model Viability" in res6["answer"]

    agent.close()
    db.close()
