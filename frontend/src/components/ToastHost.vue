<script setup lang="ts">
import { toasts, dismissToast } from '../composables/toast'
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <div
      v-for="t in toasts"
      :key="t.id"
      class="fd-toast"
      :class="`fd-toast-${t.kind}`"
      role="status"
      @click="dismissToast(t.id)"
    >
      <span class="toast-icon" aria-hidden="true">{{ { success: '✓', warning: '!', error: '✕', info: '●' }[t.kind] }}</span>
      <span class="toast-text">{{ t.text }}</span>
      <span class="toast-close" aria-hidden="true">×</span>
    </div>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  pointer-events: none;
}
.fd-toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 220px;
  max-width: 380px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.5;
  cursor: pointer;
  color: var(--fd-ink-900);
  background: var(--fd-surface);
  border: var(--fd-border);
  border-radius: var(--fd-r-sm);
  box-shadow: var(--fd-e2);
  animation: fd-toast-in var(--fd-dur) var(--fd-ease-pop);
}
.fd-toast:hover { transform: translate(-2px, -2px); box-shadow: var(--fd-e3); }
.toast-icon {
  flex: none;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: var(--fd-r-sm);
  font-size: 11px;
  font-weight: 700;
  color: #fff;
}
.toast-text { flex: 1; min-width: 0; }
.toast-close { flex: none; color: var(--fd-ink-400); font-size: 14px; }
.fd-toast-success .toast-icon { background: var(--fd-ok); }
.fd-toast-warning .toast-icon { background: var(--fd-warn); }
.fd-toast-error   .toast-icon { background: var(--fd-danger); }
.fd-toast-info    .toast-icon { background: var(--fd-accent-600); }
@keyframes fd-toast-in {
  from { opacity: 0; transform: translateX(16px); }
  to   { opacity: 1; transform: translateX(0); }
}
@media (prefers-reduced-motion: reduce) {
  .fd-toast { animation: none; }
}
</style>
