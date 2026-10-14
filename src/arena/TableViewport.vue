<script setup lang="ts">
import {ref} from 'vue'
import MahjongTable3D from '../components/MahjongTable3D.vue'
import type {TableProps} from '../components/table/three/tableRenderTypes'
const props = withDefaults(defineProps<TableProps>(), {showOwnHand: true})
const emit = defineEmits<{ready: []; loadError: [message: string]}>()
const zoom = ref(1), panX = ref(0), panY = ref(0), dragging = ref(false)
let pointer: number | null = null, lastX = 0, lastY = 0
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
function wheel(e: WheelEvent) {
  if (!(e.target instanceof HTMLCanvasElement)) return
  e.preventDefault()
  const pixels = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? e.currentTarget instanceof HTMLElement ? e.currentTarget.clientHeight : 600 : 1)
  zoom.value = clamp(zoom.value * Math.exp(-clamp(pixels, -300, 300) * .0015), .6, 2.4)
}
function down(e: PointerEvent) {
  if (e.button !== 0 || !(e.target instanceof HTMLCanvasElement) || pointer !== null) return
  e.preventDefault()
  pointer = e.pointerId; lastX = e.clientX; lastY = e.clientY; dragging.value = true
  e.target.setPointerCapture(e.pointerId)
}
function move(e: PointerEvent) {
  if (pointer !== e.pointerId) return
  const height = Math.max(1, (e.currentTarget as HTMLElement).clientHeight)
  panX.value = clamp(panX.value - (e.clientX - lastX) / height, -1.5, 1.5)
  panY.value = clamp(panY.value + (e.clientY - lastY) / height, -1.5, 1.5)
  lastX = e.clientX; lastY = e.clientY
}
function up(e: PointerEvent) {
  if (pointer !== e.pointerId) return
  pointer = null; dragging.value = false
  if ((e.target as Element).hasPointerCapture?.(e.pointerId)) (e.target as Element).releasePointerCapture(e.pointerId)
}
function reset() {zoom.value = 1; panX.value = 0; panY.value = 0}
</script>

<template>
  <div class="table-viewport" :class="{dragging}" @wheel="wheel" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up">
    <MahjongTable3D v-bind="props" :camera-scale="(props.cameraScale ?? 1.16) / zoom" :camera-pan-x="panX" :camera-pan-y="panY" @ready="emit('ready')" @load-error="emit('loadError', $event)"/>
    <div class="view-controls"><span>滚轮缩放 · 按住左键拖动</span><output aria-label="缩放比例">{{ Math.round(zoom * 100) }}%</output><button class="quiet" @click="reset">重置视角</button></div>
  </div>
</template>

<style scoped>
.table-viewport {position:absolute;inset:0;overflow:hidden}
.table-viewport :deep(canvas) {cursor:grab;touch-action:none}
.table-viewport.dragging :deep(canvas) {cursor:grabbing}
.view-controls {position:absolute;right:16px;bottom:12px;display:flex;align-items:center;gap:12px;font-size:11px;color:#c0cebd;background:#102b26db;border-radius:8px;padding:2px 10px;user-select:none}
@media(max-width:760px){.view-controls span{display:none}}
</style>
