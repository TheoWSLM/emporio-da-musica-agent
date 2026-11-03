import { reactive, ref } from "vue";
import { ApiError, api } from "../api/client";
import type { Assessment, HistoryMessage, SseEvent } from "../api/types";

export interface ToolTrace {
  name: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  duration_ms: number;
  output?: Record<string, unknown>;
}

export interface TurnTrace {
  question: string;
  classification?: { provider: string; latency_ms: number; assessment: Assessment; route: string; reason: string; flags: string[] };
  tools: ToolTrace[];
  citations: string[];
  outcome?: string;
  latency_ms?: number;
  model_rounds?: number;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  outcome?: string;
  suggestions: string[];
  trace?: TurnTrace;
  error?: boolean;
}

const STORAGE_KEY = "emporio.conversation";
let nextId = 1;

export function useChat() {
  const conversationId = ref<string | null>(null);
  const messages = ref<ChatMessage[]>([]);
  const traces = ref<TurnTrace[]>([]);
  const busy = ref(false);
  const status = ref<string | null>(null);

  async function newConversation() {
    const { conversation_id } = await api.createConversation();
    conversationId.value = conversation_id;
    localStorage.setItem(STORAGE_KEY, conversation_id);
    messages.value = [];
    traces.value = [];
  }

  function traceFromHistory(question: string, details: Record<string, unknown>): TurnTrace {
    const classification = details.classification as (Assessment & { provider: string; latency_ms: number }) | undefined;
    return {
      question,
      classification: classification
        ? { provider: classification.provider, latency_ms: classification.latency_ms, assessment: classification, route: String(details.route ?? ""), reason: "", flags: [] }
        : undefined,
      tools: (details.tools as ToolTrace[] | undefined) ?? [],
      citations: (details.cited_sections as string[] | undefined) ?? [],
      outcome: details.outcome as string | undefined,
    };
  }

  async function restore() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return newConversation();
    try {
      const { messages: history } = await api.history(saved);
      conversationId.value = saved;
      let lastQuestion = "";
      for (const m of history as HistoryMessage[]) {
        if (m.role === "user") {
          lastQuestion = m.content;
          messages.value.push({ id: nextId++, role: "user", text: m.content, suggestions: [] });
        } else {
          const trace = traceFromHistory(lastQuestion, m.details);
          traces.value.push(trace);
          messages.value.push({ id: nextId++, role: "assistant", text: m.content, outcome: trace.outcome, suggestions: [], trace });
        }
      }
    } catch {
      await newConversation();
    }
  }

  function apply(event: SseEvent, trace: TurnTrace, reply: ChatMessage) {
    switch (event.type) {
      case "classification":
        trace.classification = { provider: event.provider, latency_ms: event.latency_ms, assessment: event.assessment, route: event.route, reason: event.reason, flags: event.heuristic_flags };
        break;
      case "status":
        status.value = event.text;
        break;
      case "tool":
        trace.tools.push({ name: event.name, arguments: event.arguments, ok: event.ok, duration_ms: event.duration_ms, output: event.output });
        break;
      case "message":
        reply.text = event.reply.message;
        reply.outcome = event.outcome;
        reply.suggestions = event.reply.suggested_replies.slice(0, 3);
        trace.citations = event.reply.cited_sections;
        trace.outcome = event.outcome;
        break;
      case "done":
        trace.latency_ms = event.latency_ms;
        trace.model_rounds = event.model_rounds;
        break;
      case "error":
        reply.text = event.detail;
        reply.error = true;
        break;
    }
  }

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy.value || !conversationId.value) return;
    busy.value = true;
    status.value = "Lendo sua mensagem…";
    messages.value.forEach((m) => (m.suggestions = []));
    messages.value.push({ id: nextId++, role: "user", text: content, suggestions: [] });
    const trace = reactive<TurnTrace>({ question: content, tools: [], citations: [] });
    traces.value.push(trace);
    const reply = reactive<ChatMessage>({ id: nextId++, role: "assistant", text: "", suggestions: [], trace });
    try {
      for await (const event of api.send(conversationId.value, content)) apply(event, trace, reply);
    } catch (error) {
      reply.text = error instanceof ApiError ? error.message : "Não consegui me conectar agora. Tente novamente.";
      reply.error = true;
    } finally {
      if (!reply.text) {
        reply.text = "Não recebi resposta. Tente novamente.";
        reply.error = true;
      }
      messages.value.push(reply);
      busy.value = false;
      status.value = null;
    }
  }

  return { messages, traces, busy, status, restore, send, newConversation };
}
