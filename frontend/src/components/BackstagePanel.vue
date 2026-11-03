<script setup lang="ts">
import { computed } from "vue";
import type { PublicConfig } from "../api/types";
import { INTENT_LABELS } from "../composables/format";
import type { TurnTrace } from "../composables/useChat";

const props = defineProps<{ traces: TurnTrace[]; config: PublicConfig | null }>();
defineEmits<{ close: [] }>();
const ordered = computed(() => [...props.traces].reverse());

function args(value: Record<string, unknown>): string {
  return Object.entries(value)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}=${typeof v === "string" ? `"${v}"` : JSON.stringify(v)}`)
    .join(", ");
}
</script>

<template>
  <aside class="backstage" aria-label="Bastidores do atendimento">
    <header>
      <h2>Bastidores</h2>
      <button class="ghost small" type="button" @click="$emit('close')">✕</button>
    </header>
    <p class="hint">
      O que o agente fez em cada mensagem: a leitura do classificador, as ferramentas consultadas e as seções da
      política citadas. Todo preço, prazo e status vem dessas ferramentas.
    </p>
    <dl v-if="config" class="config">
      <div><dt>Agente</dt><dd>{{ config.agent_model }}</dd></div>
      <div><dt>Classificador</dt><dd>{{ config.classifier_model }} ({{ config.classifier_provider }})</dd></div>
      <div><dt>Embeddings</dt><dd>{{ config.embedding_model }}</dd></div>
      <div v-if="config.reference_date"><dt>Data de referência</dt><dd>{{ config.reference_date }}</dd></div>
    </dl>

    <p v-if="!traces.length" class="empty">Envie uma mensagem para ver o raciocínio aqui.</p>

    <article v-for="(trace, index) in ordered" :key="index" class="trace">
      <h3>“{{ trace.question }}”</h3>
      <div v-if="trace.classification" class="block">
        <span class="label">Classificador</span>
        <span class="chip" :class="trace.classification.route">{{ trace.classification.route }}</span>
        <span class="chip">{{ INTENT_LABELS[trace.classification.assessment.intent] ?? trace.classification.assessment.intent }}</span>
        <span class="chip">{{ trace.classification.assessment.scope }}</span>
        <span v-if="trace.classification.assessment.threat !== 'safe'" class="chip danger">{{ trace.classification.assessment.threat }}</span>
        <span class="muted">{{ trace.classification.provider }} · {{ trace.classification.latency_ms }} ms</span>
      </div>
      <div v-if="trace.tools.length" class="block">
        <span class="label">Ferramentas</span>
        <details v-for="(tool, i) in trace.tools" :key="i" class="tool">
          <summary>
            <code>{{ tool.name }}({{ args(tool.arguments) }})</code>
            <span class="muted">{{ tool.duration_ms }} ms</span>
          </summary>
          <pre v-if="tool.output">{{ JSON.stringify(tool.output, null, 2) }}</pre>
        </details>
      </div>
      <div v-else-if="trace.outcome === 'answered'" class="block">
        <span class="label">Ferramentas</span>
        <span class="muted">nenhuma — resposta com o contexto já carregado</span>
      </div>
      <div v-if="trace.citations.length" class="block">
        <span class="label">Política citada</span>
        <ul>
          <li v-for="c in trace.citations" :key="c">{{ c }}</li>
        </ul>
      </div>
      <div v-if="trace.latency_ms" class="footer muted">
        {{ (trace.latency_ms / 1000).toFixed(1) }} s · {{ trace.model_rounds }} chamada(s) ao agente · {{ trace.outcome }}
      </div>
    </article>
  </aside>
</template>
