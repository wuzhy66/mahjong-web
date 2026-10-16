<script setup lang="ts">
defineProps<{recommendation: string; probability: number; text: string; loading: boolean; error: string}>()
</script>

<template>
  <aside class="advice-panel" aria-label="AI 建议" :aria-busy="loading">
    <div class="advice-heading"><strong>AI 建议</strong><span v-if="loading" class="advice-status">{{ text ? '正在生成…' : '正在分析牌形…' }}</span></div>
    <div class="advice-recommendation"><b>{{ recommendation }}</b><span>动作概率 {{ (probability * 100).toFixed(2) }}%</span></div>
    <p v-if="text" class="advice-text">{{ text }}</p>
    <p v-else-if="loading" class="advice-placeholder">正在结合手牌解释推荐理由，可以继续出牌。</p>
    <p v-if="error" class="advice-error" role="status">{{ error }}</p>
    <small>基于可见牌局的解释 · 动作概率不代表胜率</small>
  </aside>
</template>

<style scoped>
.advice-panel{position:absolute;z-index:4;right:24px;bottom:60px;width:320px;max-width:calc(100% - 48px);padding:16px 18px;border:1px solid #d9be8380;border-radius:14px;background:#102b26f2;box-shadow:0 8px 28px #0003;font-size:13px;line-height:1.65}
.advice-heading{display:flex;align-items:center;justify-content:space-between;color:var(--gold);gap:10px;margin-bottom:8px}
.advice-status{font-size:10px;color:var(--muted)}
.advice-recommendation{display:flex;align-items:center;flex-wrap:wrap;gap:6px 12px;margin-bottom:8px;color:#f3d28a}
.advice-recommendation b{font-size:16px}.advice-recommendation span{font-size:10px;border:1px solid #d9be8360;border-radius:20px;padding:1px 7px;white-space:nowrap}
.advice-text{white-space:pre-wrap;overflow-wrap:anywhere;max-height:170px;overflow-y:auto;margin:8px 0;color:#d7e2d9}
.advice-placeholder{color:var(--muted);margin:8px 0;font-size:12px}.advice-error{color:#ffb7a6;font-size:12px;margin:8px 0}
.advice-panel small{display:block;color:#91a498;font-size:10px}
@media(max-width:1100px){.advice-panel{right:12px;bottom:60px;width:280px;padding:12px;font-size:12px}.advice-text{max-height:115px}}
@media(max-width:760px){.advice-panel{position:relative;right:auto;bottom:auto;width:auto;max-width:none;margin:0 10px 10px;flex-shrink:0}.advice-text{max-height:90px}.advice-recommendation b{font-size:14px}}
</style>
