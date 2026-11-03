<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { api } from "./api/client";
import type { PublicConfig } from "./api/types";
import BackstagePanel from "./components/BackstagePanel.vue";
import ChatMessage from "./components/ChatMessage.vue";
import MessageComposer from "./components/MessageComposer.vue";
import { useChat } from "./composables/useChat";

const EXAMPLES = [
  "Quais opções de violões disponíveis custando até R$1000?",
  "Qual o endereço da loja?",
  "Quanto custa o Takamine GD20?",
  "Me arrependi da minha compra, posso devolver meu pedido?",
];

const { messages, traces, busy, status, restore, send, newConversation } = useChat();
const config = ref<PublicConfig | null>(null);
const showBackstage = ref(window.innerWidth > 1100);
const scroller = ref<HTMLElement | null>(null);

onMounted(async () => {
  config.value = await api.config().catch(() => null);
  await restore();
});

watch(
  () => [messages.value.length, status.value],
  async () => {
    await nextTick();
    scroller.value?.scrollTo({ top: scroller.value.scrollHeight, behavior: "smooth" });
  },
);
</script>

<template>
  <div class="shell" :class="{ 'with-backstage': showBackstage }">
    <header class="topbar">
      <div class="brand">
        <span class="logo" aria-hidden="true">🎸</span>
        <div>
          <h1>Empório da Música</h1>
          <p>Sua música começa aqui.</p>
        </div>
      </div>
      <div class="actions">
        <button class="ghost" type="button" @click="newConversation">Nova conversa</button>
        <button class="ghost" type="button" :aria-pressed="showBackstage" @click="showBackstage = !showBackstage">
          {{ showBackstage ? "Ocultar bastidores" : "Ver bastidores" }}
        </button>
      </div>
    </header>

    <main class="chat">
      <section ref="scroller" class="messages" aria-live="polite">
        <div v-if="!messages.length" class="welcome">
          <div class="avatar large" aria-hidden="true">L</div>
          <h2>Oi! Eu sou a Lia 👋</h2>
          <p>
            Assistente virtual da Empório da Música. Posso ajudar com instrumentos, preços, pedidos, pagamentos,
            trocas, entregas e horários da loja.
          </p>
          <div class="examples">
            <button v-for="example in EXAMPLES" :key="example" type="button" @click="send(example)">{{ example }}</button>
          </div>
        </div>

        <ChatMessage v-for="message in messages" :key="message.id" :message="message" @suggest="send" />

        <div v-if="busy" class="typing">
          <div class="avatar" aria-hidden="true">L</div>
          <div class="bubble pending">
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span>
            <span>{{ status }}</span>
          </div>
        </div>
      </section>

      <MessageComposer :disabled="busy" @send="send" />
      <p class="disclaimer">
        Demonstração técnica — loja fictícia. Respostas geradas por IA com dados verificados pelas ferramentas da loja.
      </p>
    </main>

    <BackstagePanel v-if="showBackstage" :traces="traces" :config="config" @close="showBackstage = false" />
  </div>
</template>
