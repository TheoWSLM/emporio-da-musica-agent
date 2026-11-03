// Minimal, safe formatting for WhatsApp-style replies: escape first, then **bold**, "- " lists, line breaks.

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function inline(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

export function renderMessage(raw: string): string {
  const lines = escapeHtml(raw.trim()).split("\n");
  const html: string[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) html.push(`<ul>${list.map((item) => `<li>${inline(item)}</li>`).join("")}</ul>`);
    list = [];
  };
  for (const line of lines) {
    const item = line.match(/^\s*[-•]\s+(.*)$/);
    if (item) {
      list.push(item[1]);
      continue;
    }
    flush();
    if (line.trim()) html.push(`<p>${inline(line)}</p>`);
  }
  flush();
  return html.join("");
}

export const INTENT_LABELS: Record<string, string> = {
  product_search: "busca de produto",
  price_payment: "preço / pagamento",
  order_status: "status de pedido",
  return_exchange: "troca / devolução",
  shipping: "frete",
  store_info: "informações da loja",
  warranty: "garantia",
  complaint: "reclamação",
  human_handoff: "atendimento humano",
  other: "outro",
};
