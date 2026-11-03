import type { HistoryMessage, PublicConfig, SseEvent } from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : "Erro de comunicação.");
  }
  return response.json() as Promise<T>;
}

export const api = {
  config: () => fetch(`${BASE}/config`).then((r) => json<PublicConfig>(r)),
  createConversation: () =>
    fetch(`${BASE}/conversations`, { method: "POST" }).then((r) => json<{ conversation_id: string }>(r)),
  history: (id: string) =>
    fetch(`${BASE}/conversations/${id}`).then((r) => json<{ messages: HistoryMessage[] }>(r)),

  /** POSTs a message and yields the Server-Sent Events of the turn (EventSource cannot POST). */
  async *send(id: string, content: string): AsyncGenerator<SseEvent> {
    const response = await fetch(`${BASE}/conversations/${id}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ content }),
    });
    if (!response.ok || !response.body) {
      await json(response);
      return;
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = block
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (data) yield JSON.parse(data) as SseEvent;
      }
    }
  },
};
