<script setup lang="ts">
import { computed } from "vue";
import type { ChatMessage } from "../composables/useChat";
import { renderMessage } from "../composables/format";

const props = defineProps<{ message: ChatMessage }>();
defineEmits<{ suggest: [text: string] }>();
const html = computed(() => renderMessage(props.message.text));
const badge = computed(() => {
  switch (props.message.outcome) {
    case "blocked":
      return "mensagem bloqueada pela proteção";
    case "off_topic":
      return "fora do escopo da loja";
    case "fallback":
      return "resposta segura (encaminhamento)";
    default:
      return null;
  }
});
</script>

<template>
  <div class="row" :class="message.role">
    <div v-if="message.role === 'assistant'" class="avatar" aria-hidden="true">L</div>
    <div class="stack">
      <div class="bubble" :class="{ error: message.error }">
        <div v-if="message.role === 'assistant'" class="content" v-html="html"></div>
        <div v-else class="content">{{ message.text }}</div>
      </div>
      <div v-if="message.role === 'assistant' && (badge || message.trace?.citations.length)" class="meta">
        <span v-if="badge" class="tag warn">{{ badge }}</span>
        <span v-for="section in message.trace?.citations" :key="section" class="tag">📄 {{ section.split(' > ').pop() }}</span>
      </div>
      <div v-if="message.suggestions.length" class="suggestions">
        <button v-for="s in message.suggestions" :key="s" type="button" @click="$emit('suggest', s)">{{ s }}</button>
      </div>
    </div>
  </div>
</template>
