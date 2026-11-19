<template>
  <router-view />
</template>

<style>
/* 全局基底：FOLD 的 body 样式按 fd-root 类生效 */
body.fd-root,
body {
  font-family: var(--fd-font, "PingFang SC", "Microsoft YaHei", sans-serif);
  background: var(--fd-paper, #f5f4ee);
  color: var(--fd-ink-900, #23282f);
  margin: 0;
  -webkit-font-smoothing: antialiased;
}
</style>
