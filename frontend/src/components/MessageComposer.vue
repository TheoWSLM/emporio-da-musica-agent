<script setup lang="ts">
import { ref } from "vue";

defineProps<{ disabled: boolean }>();
const emit = defineEmits<{ send: [text: string] }>();
const text = ref("");
const MAX = 2000;

function submit() {
  if (!text.value.trim()) return;
  emit("send", text.value);
  text.value = "";
}

function onKey(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submit();
  }
}
</script>

<template>
  <form class="composer" @submit.prevent="submit">
    <label class="sr-only" for="message">Mensagem</label>
    <textarea
      id="message"
      v-model="text"
      rows="1"
      :maxlength="MAX"
      placeholder="Escreva sua mensagem…"
      :disabled="disabled"
      @keydown="onKey"
    ></textarea>
    <button type="submit" :disabled="disabled || !text.trim()" aria-label="Enviar">➤</button>
  </form>
</template>
