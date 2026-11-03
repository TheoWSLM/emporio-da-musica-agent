"""Fixed replies used when the agent must not (or need not) be called."""

from emporio.conversation.domain.models import RESPONSE_SLA
from emporio.store.domain.info import EMPORIO

BLOCKED = (
    "Desculpe, nisso eu não posso ajudar. 🙂 Sou a Lia, assistente da Empório da Música, e posso te ajudar "
    "com instrumentos, preços, pedidos, pagamentos, trocas, entregas e informações da loja. Como posso ajudar?"
)
OFF_TOPIC = (
    "Essa eu vou ficar devendo! 😅 Por aqui eu ajudo com tudo sobre a Empório da Música: instrumentos, "
    "preços, pedidos, trocas, entregas e horários da loja. Posso te ajudar com alguma dessas coisas?"
)
FALLBACK = (
    "Desculpe, não consegui montar uma resposta confiável agora e prefiro não te passar nenhuma informação "
    f"errada. Posso registrar seu atendimento para a nossa equipe, que retorna em até {RESPONSE_SLA}, ou "
    f"você pode falar com a gente pelo WhatsApp {EMPORIO.whatsapp}. Quer que eu registre?"
)
SUGGESTIONS = [
    "Quais violões vocês têm até R$ 1.000?",
    "Qual o horário de funcionamento?",
    "Quero saber o status do meu pedido",
]
