// Mirrors backend/src/emporio/api/schemas.py (the SSE discriminated union and REST payloads).

export interface CustomerReply {
  message: string;
  cited_sections: string[];
  needs_human: boolean;
  suggested_replies: string[];
}

export interface Assessment {
  threat: string;
  threat_confidence: string;
  scope: string;
  scope_confidence: string;
  intent: string;
  frustration: string;
  wants_human: boolean;
}

export type SseEvent =
  | { type: "classification"; provider: string; latency_ms: number; assessment: Assessment; route: string; reason: string; heuristic_flags: string[] }
  | { type: "status"; text: string }
  | { type: "tool"; name: string; arguments: Record<string, unknown>; ok: boolean; duration_ms: number; output: Record<string, unknown> }
  | { type: "message"; reply: CustomerReply; outcome: "answered" | "blocked" | "off_topic" | "fallback" }
  | { type: "done"; outcome: string | null; latency_ms: number; model_rounds: number }
  | { type: "error"; detail: string };

export interface PublicConfig {
  agent_model: string;
  classifier_provider: "openai" | "jev";
  classifier_model: string;
  embedding_model: string;
  reference_date: string | null;
  release: string;
}

export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
  details: Record<string, unknown>;
}
