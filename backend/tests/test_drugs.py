"""OC-09 tests — drug compare / generics (pure unit tests over CSV)."""
import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from services import drugs


def test_exact_brand_match():
    row = drugs.match_drug("Dolo 650")
    assert row is not None
    assert row["generic_name"] == "Paracetamol"


def test_case_insensitive():
    assert drugs.match_drug("dolo 650")["generic_name"] == "Paracetamol"


def test_fuzzy_match_minor_typo():
    # 'Dolo 625' vs 'Dolo 650' should fuzzy-match
    row = drugs.match_drug("Dolo 625")
    assert row is not None


def test_generic_name_lookup():
    row = drugs.match_drug("Paracetamol")
    assert row is not None
    assert row["generic_name"] == "Paracetamol"


def test_no_match_returns_none():
    assert drugs.match_drug("zzznotadrug") is None


def test_compare_savings():
    out = drugs.compare(["Telma 40", "Unknownmed 500"])
    assert out[0]["found"] is True
    assert out[0]["saving"] > 0
    assert out[0]["generic_name"] == "Telmisartan"
    assert out[1]["found"] is False


def test_generics_for_molecule():
    gens = drugs.generics_for("Augmentin 625")
    assert gens
    assert all(g["generic_name"] == "Amoxicillin+Clavulanate" for g in gens)


@pytest.mark.asyncio
async def test_compare_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/drugs/compare", json={"drug_names": ["Azithral 500", "Pantocid 40"]})
        assert r.status_code == 200
        data = r.json()["drugs"]
        assert data[0]["brand_price"] == 48.5
        assert data[0]["generic_price"] == 15.0
        assert data[1]["generic_name"] == "Pantoprazole"


@pytest.mark.asyncio
async def test_generics_endpoint_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/drugs/generics/notadrug")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_generics_endpoint_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/drugs/generics/Crocin Advance 500")
        assert r.status_code == 200
        assert r.json()["generics"][0]["generic_name"] == "Paracetamol"
