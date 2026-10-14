<script setup lang="ts">
import {computed, onBeforeUnmount, onMounted, ref, watch} from 'vue'
import TableViewport from './TableViewport.vue'
import MahjongTile from '../components/MahjongTile.vue'
import type {Replay} from './api'
import type {TileType} from '../game/core/contracts/types'
const props = defineProps<{replay: Replay}>()
const emit = defineEmits<{close: []}>()
const panel = ref<HTMLElement | null>(null)
const previousFocus = document.activeElement as HTMLElement | null
onMounted(() => panel.value?.focus())
const index = ref(0), seat = ref(0), playing = ref(false), sceneError = ref('')
const names = ['本家', '下家', '对家', '上家']
const frame = computed(() => props.replay.frames[index.value]!)
const state = computed(() => frame.value.snapshot)
const wall = computed<TileType[]>(() => Array(state.value.wallCount).fill('white'))
let timer: ReturnType<typeof setInterval> | undefined
function stop() {playing.value = false; clearInterval(timer)}
function seek(i: number) {stop(); index.value = Math.max(0, Math.min(props.replay.frames.length - 1, i))}
function play() {
  if (playing.value) return stop()
  if (index.value === props.replay.frames.length - 1) index.value = 0
  playing.value = true
  timer = setInterval(() => {
    if (index.value < props.replay.frames.length - 1) index.value++
    if (index.value === props.replay.frames.length - 1) stop()
  }, 900)
}
function key(e: KeyboardEvent) {
  if ((e.target as HTMLElement).matches('input,select')) return
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {e.preventDefault();seek(index.value + (e.key === 'ArrowRight' ? 1 : -1))}
  if (e.key === 'Escape') emit('close')
}
watch(() => props.replay, () => seek(0))
onBeforeUnmount(() => {stop(); if (previousFocus?.isConnected) previousFocus.focus()})
</script>

<template>
  <section ref="panel" class="replay-panel" role="dialog" aria-modal="true" aria-label="明牌复盘" tabindex="-1" @keydown="key">
    <header class="replay-header"><div><strong>第 {{ replay.round }} 局 · 明牌复盘</strong><small>全部玩家手牌公开 · 每步包含该次决策及随后的自动摸牌</small></div><button @click="emit('close')">退出复盘</button></header>
    <div class="scene replay-scene">
      <TableViewport :players="state.players" :wall="wall" :wall-count="state.wallCount" :wall-head-drawn="state.wallHeadDrawn" :last-discard="state.lastDiscard" :current-player="state.currentPlayer" :dealer-index="state.dealer" :reveal-hands="true" :joker-tiles="['white']" joker-label="财" @load-error="sceneError=$event"/>
      <div class="round-bar">庄家 · {{ names[state.dealer] }}　可摸 {{ state.drawable }} 张</div>
      <div v-for="p in state.players.slice(1)" :key="p.seat" class="seat-card" :class="'seat-'+p.seat"><strong>{{ names[p.seat] }} · {{ p.name }}</strong></div>
      <div v-if="sceneError" class="scene-notice" role="alert">{{ sceneError }}</div>
    </div>
    <div class="replay-controls">
      <div class="replay-description" aria-live="polite"><strong>{{ frame.label }}</strong><span>{{ frame.events.join(' · ') }}</span><output aria-label="复盘步数">{{ index }} / {{ replay.frames.length - 1 }}</output></div>
      <input aria-label="复盘进度" type="range" min="0" :max="replay.frames.length-1" :value="index" @input="seek(Number(($event.target as HTMLInputElement).value))">
      <div class="replay-buttons"><button :disabled="index===0" @click="seek(0)">开局</button><button :disabled="index===0" @click="seek(index-1)">上一步</button><button @click="play">{{ playing ? '暂停' : '播放' }}</button><button :disabled="index===replay.frames.length-1" @click="seek(index+1)">下一步</button><button :disabled="index===replay.frames.length-1" @click="seek(replay.frames.length-1)">结算</button><label>查看手牌 <select v-model.number="seat" aria-label="查看手牌座位"><option v-for="(name,i) in names" :key="i" :value="i">{{ name }}</option></select></label></div>
      <div class="replay-hand" :aria-label="names[seat]+'明牌手牌'"><MahjongTile v-for="(tile,i) in state.players[seat]!.hand" :key="i" :tile="tile" disabled small :joker-tiles="['white']" joker-label="财"/></div>
      <div v-if="state.finished" class="replay-result">{{ state.result?.draw ? '流局' : names[state.result?.winner ?? 0]+'自摸' }} · 本局积分 {{ state.result?.scores.join(' / ') }}</div>
    </div>
  </section>
</template>

<style scoped>
.replay-panel{position:fixed;inset:0;z-index:50;background:#102b26;display:flex;flex-direction:column;outline:none}
.replay-header{display:flex;justify-content:space-between;align-items:center;padding:14px 24px;border-bottom:1px solid #ffffff20;gap:16px}
.replay-header small{display:block;color:var(--muted);font-size:11px;margin-top:6px}
.replay-controls{padding:12px 24px 18px;background:#15382e;border-top:1px solid #ffffff20}
.replay-description{display:flex;gap:16px;align-items:center;font-size:13px;min-height:24px}
.replay-description span{color:var(--muted)}.replay-description output{margin-left:auto;white-space:nowrap}
.replay-controls input{width:100%;accent-color:var(--gold);margin:12px 0}
.replay-buttons{display:flex;justify-content:center;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px}
.replay-buttons button{padding:8px 14px}.replay-buttons select{background:#294637;color:inherit;border-radius:4px;padding:6px}
.replay-hand{display:flex;justify-content:center;gap:3px;margin-top:14px;min-height:48px}
.replay-result{text-align:center;color:var(--gold);font-size:12px;margin-top:14px}
@media(max-width:760px){.replay-header{padding:10px}.replay-header small{max-width:230px}.replay-controls{padding:10px}.replay-description{flex-wrap:wrap;gap:4px}.replay-buttons{gap:4px}.replay-buttons button{padding:6px 8px}.replay-hand :deep(.mahjong-tile){--tile-width:5.6vw}}
</style>
