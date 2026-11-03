import pytest

from emporio.catalog.domain.models import Category
from emporio.catalog.domain.scope import detect_accessory, resolve_categories
from emporio.catalog.domain.specs import readable_specs

CATEGORIES = [
    Category(5, "Violões", "", ("violão", "violao")),
    Category(9, "Ukuleles", "", ("ukulele", "uke")),
]


@pytest.mark.parametrize(
    ("text", "accessory"),
    [
        ("vocês vendem cordas para violão?", "cordas"),
        ("tem palheta?", "palheta"),
        ("preciso de um AMPLIFICADOR", "amplificador"),
        ("violão de 7 cordas", None),  # describes an instrument
        ("violão com cordas de nylon", None),
        ("instrumentos de cordas orquestrais", None),
        ("quero um ukulele", None),
    ],
)
def test_accessory_detection(text: str, accessory: str | None) -> None:
    assert detect_accessory(text) == accessory


def test_category_resolution_uses_synonyms_and_ignores_accents() -> None:
    assert [c.id for c in resolve_categories("quero um violao barato", CATEGORIES)] == [5]
    assert [c.id for c in resolve_categories("uke soprano", CATEGORIES)] == [9]
    assert resolve_categories("bateria", CATEGORIES) == []


def test_readable_specs() -> None:
    assert readable_specs({"strings": "6", "body": "Alder"}) == ["6 cordas", "corpo: Alder"]
    assert readable_specs({"strings": "steel", "electronics": "yes"}) == [
        "cordas de aço",
        "eletroacústico (com captação)",
    ]
