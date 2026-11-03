from pathlib import Path

from emporio.knowledge.infrastructure.chunking import semantic_split, structural_chunks, to_chunks
from emporio.knowledge.infrastructure.pdf_parser import Element, Kind, parse_pdf

PDF = Path(__file__).resolve().parents[4] / "data" / "raw" / "store_policies.pdf"


def chunks():  # type: ignore[no-untyped-def]
    return to_chunks(structural_chunks(parse_pdf(PDF)))


def test_one_chunk_per_subsection_with_heading_path() -> None:
    paths = [c.section_path for c in chunks()]

    assert (
        "4. Política de Trocas e Devoluções > 4.1 Direito de Arrependimento (Compras Online)"
        in paths
    )
    assert "2. Horário de Funcionamento" in paths
    assert len(paths) == 25


def test_tables_are_kept_whole_as_markdown() -> None:
    hours = next(c for c in chunks() if c.heading == "2. Horário de Funcionamento")

    assert "|Sábado|09:00 às 13:00|" in hours.content
    assert "|Domingo e Feriados|Fechado|" in hours.content


def test_running_headers_footers_and_cover_are_removed() -> None:
    text = "\n".join(c.content for c in chunks())

    assert "Manual de Políticas e Procedimentos" not in text
    assert "Página " not in text
    assert "​" not in text


def test_section_spanning_two_pages_stays_together() -> None:
    other_cities = next(c for c in chunks() if c.heading.startswith("5.2"))

    assert "|SEDEX (Correios)|2 a 5 dias úteis|" in other_cities.content
    assert "cotação individual" in other_cities.content


def test_numbered_list_items_are_not_mistaken_for_sections() -> None:
    flow = next(c for c in chunks() if c.heading.startswith("7.2"))

    assert "1. Saudação" in flow.content and "5. Fechamento" in flow.content


def test_structural_chunking_from_elements() -> None:
    elements = [
        Element(Kind.SECTION, "1. A"),
        Element(Kind.TEXT, "intro que continua"),
        Element(Kind.TEXT, "na linha de baixo."),
        Element(Kind.SUBSECTION, "1.1 B"),
        Element(Kind.TEXT, "- item"),
    ]

    result = to_chunks(structural_chunks(elements))

    assert [(c.section_path, c.content) for c in result] == [
        ("1. A", "intro que continua na linha de baixo."),
        ("1. A > 1.1 B", "- item"),
    ]


def test_semantic_split_cuts_at_the_weakest_link() -> None:
    paragraphs = ["a" * 400, "b" * 400, "c" * 400]
    embeddings = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]

    pieces = semantic_split(paragraphs, embeddings, max_tokens=250)

    assert pieces == ["a" * 400 + "\n" + "b" * 400, "c" * 400]
