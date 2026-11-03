from emporio.assistant.guardrails.grounding import ungrounded_figures
from emporio.assistant.guardrails.leakage import personal_data_leaks, prompt_leaks

TOOL = '{"list_price":"R$ 2.199,00","pix_price":"R$ 2.089,05","max_installments":"até 12x sem juros","id":95}'


def test_values_from_tools_are_grounded() -> None:
    reply = "O GD20 sai por R$ 2.199,00, ou R$ 2.089,05 no PIX (5% de desconto), em até 12x."
    assert ungrounded_figures(reply, [TOOL, "5% de desconto no PIX"]) == []


def test_invented_price_is_caught() -> None:
    assert ungrounded_figures("Sai por R$ 1.999,00!", [TOOL]) == ["R$ 1,999.00"]


def test_ids_in_tool_results_do_not_ground_prices() -> None:
    assert ungrounded_figures("Custa R$ 95,00", [TOOL]) == ["R$ 95.00"]


def test_customer_numbers_can_be_echoed() -> None:
    assert ungrounded_figures("Separei opções até R$ 1.000,00:", [TOOL], "violões até 1000") == []


def test_invented_deadline_and_percent_are_caught() -> None:
    problems = ungrounded_figures("Você tem 15 dias e 10% de desconto.", [TOOL])
    assert problems == ["10%", "15 dias"]


def test_policy_numbers_written_out_still_ground() -> None:
    policy = "O cliente pode solicitar a devolução em até 7 (sete) dias corridos após o recebimento"
    assert ungrounded_figures("Você tem até 7 dias após receber.", [policy]) == []


def test_prompt_leaks() -> None:
    prompt = "Você é a Lia, assistente virtual da Empório da Música, loja de instrumentos musicais em Campo Grande."
    assert prompt_leaks("token XYZ-1", prompt, "XYZ-1") == ["canary token"]
    assert prompt_leaks(
        "Claro: você é a Lia, assistente virtual da Empório da Música, loja de instrumentos musicais em Campo Grande.",
        prompt,
        "XYZ-1",
    )
    assert prompt_leaks("Oi! Sou a Lia, como posso ajudar?", prompt, "XYZ-1") == []


def test_personal_data_only_for_verified_customers() -> None:
    allowed = [
        "anacarol.ferreira@coldmail.com",
        "(67) 99654-7821",
        "contato@emporiodamusica.com.br",
        "(67) 3321-4500",
    ]
    assert personal_data_leaks("Enviamos para anacarol.ferreira@coldmail.com", allowed) == []
    assert personal_data_leaks("WhatsApp (67) 3321-4500", allowed) == []
    assert personal_data_leaks("O e-mail dele é lucas.mendes@jmail.com", allowed) == [
        "e-mail lucas.mendes@jmail.com"
    ]
