<script setup lang="ts">
import {computed, onMounted, onBeforeUnmount, ref, watch} from 'vue'
import TableViewport from './TableViewport.vue'
import ReplayPanel from './ReplayPanel.vue'
import RulesPanel from './RulesPanel.vue'
import AdvicePanel from './AdvicePanel.vue'
import MahjongTile from '../components/MahjongTile.vue'
import {ApiError, request, streamHint, type Catalog, type Snapshot, type Replay, type Hint} from './api'
import type {TileType} from '../game/core/contracts/types'
import {tileName} from '../game/core/rules/tiles'

const hint = ref<Hint | null>(null), hintDifficulty = ref('astra-0'), hintError = ref(''), hintLoading = ref(false)
const adviceText = ref(''), adviceLoading = ref(false), adviceError = ref('')
let adviceController: AbortController | undefined
const hintScores = computed(() => new Map(hint.value?.actions.map(a => [a.id, a.probability]) ?? []))
const bestHintAction = computed(() => hint.value?.actions.reduce((best, a) => a.probability > best.probability ? a : best).id)
const recommended = computed(() => {
  const action = room.value?.legalActions.find(a => a.id === bestHintAction.value)
  const label = action?.kind === 'discard' && action.tile ? `建议打出「${tileName(action.tile)}」` : `建议${action?.label ?? ''}`
  return {label, probability: hintScores.value.get(action?.id ?? -1) ?? 0}
})
function clearHint() {
  adviceController?.abort(); adviceController = undefined
  hint.value = null; hintError.value = ''; adviceText.value = ''; adviceError.value = ''
  adviceLoading.value = false; hintLoading.value = false
}
watch(hintDifficulty, clearHint)
function score(actionId?: number) {
  const value = actionId === undefined ? undefined : hintScores.value.get(actionId)
  return value === undefined ? '—' : (value * 100).toFixed(2) + '%'
}
function tileScore(tile: TileType) {return score(room.value?.legalActions.find(a => a.kind === 'discard' && a.tile === tile)?.id)}
async function requestHint() {
  if (busy.value || !ownTurn.value || !room.value || replay.value) return
  const id = room.value.id, revision = room.value.revision, difficulty = hintDifficulty.value
  clearHint(); clearTimeout(timer)
  const controller = new AbortController(); adviceController = controller
  busy.value = true; hintLoading.value = true; adviceLoading.value = true
  try {
    await streamHint(`/rooms/${id}/hint-stream`, token, {revision, difficulty}, controller.signal, event => {
      if (disposed || controller.signal.aborted || room.value?.id !== id || room.value.revision !== revision || hintDifficulty.value !== difficulty) return
      if (event.type === 'hint') {
        if (event.data.revision !== revision || event.data.difficulty !== difficulty) throw new Error('提示状态不匹配，请重试')
        hint.value = event.data
        const discards = room.value.legalActions.filter(a => a.kind === 'discard')
        const best = discards.reduce<Snapshot['legalActions'][number] | undefined>((b, a) => !b || (hintScores.value.get(a.id) ?? 0) > (hintScores.value.get(b.id) ?? 0) ? a : b, undefined)
        selected.value = best ? hand.value.findIndex(t => t === best.tile) : -1
        busy.value = false; hintLoading.value = false; schedule()
      } else if (event.type === 'delta') adviceText.value += event.data.text
      else if (event.type === 'error') {adviceError.value = event.data.message; adviceLoading.value = false}
      else if (event.type === 'done') adviceLoading.value = false
    })
  } catch(e) {
    if (controller.signal.aborted) return
    const message = e instanceof Error ? e.message : 'AI 建议失败，请重试'
    if (hint.value) adviceError.value = message
    else hintError.value = message
  } finally {
    if (adviceController === controller) {
      adviceController = undefined; busy.value = false; hintLoading.value = false; adviceLoading.value = false; schedule()
    }
  }
}
const replay = ref<Replay | null>(null)
const catalog = ref<Catalog | null>(null)
const room = ref<Snapshot | null>(null)
const difficulties = ref(['easy', 'medium', 'hard'])
const busy = ref(false), error = ref(''), selected = ref(-1), ready = ref(false), sceneError = ref(''), sceneKey = ref(0)
const showResult = ref(true), showRules = ref(false)
let token = '', timer: ReturnType<typeof setTimeout> | undefined, disposed = false
const seats = ['本家', '下家', '对家', '上家']
const rule = computed(() => catalog.value?.rules.find(r => r.id === (room.value?.ruleId ?? catalog.value?.defaultRule)))
const hand = computed(() => room.value?.players[0]?.hand ?? [])
const ownTurn = computed(() => room.value?.currentPlayer === 0 && !room.value.finished)
const discard = computed(() => room.value?.legalActions.find(a => a.kind === 'discard' && a.tile === hand.value[selected.value]))
const choices = computed(() => {
  const claimed = room.value?.lastDiscard?.tile
  return (room.value?.legalActions.filter(a => a.kind !== 'discard') ?? []).map(action => ({
    ...action,
    labelParts: action.label.split(/(\s+)/).map(text => ({
      text, claimed: action.kind === 'chi' && claimed !== undefined && text === tileName(claimed),
    })),
  }))
})
// 仅提供牌背占位；真实牌墙与 seed 永远不下发浏览器。
const wall = computed<TileType[]>(() => Array(room.value?.wallCount ?? 0).fill('white'))
const status = computed(() => room.value?.finished ? '本局结束' : ownTurn.value ? '轮到你了' : `${seats[room.value?.currentPlayer ?? 0]}正在思考`)
const signed = (n: number) => n > 0 ? '+' + n : String(n)
function schedule() {
  clearTimeout(timer)
  if (disposed || replay.value || !room.value || room.value.finished || error.value) return
  if (ownTurn.value) {
    const actions = room.value.legalActions
    if (actions.length === 1 && actions[0]?.kind === 'pass') timer = setTimeout(() => void command('action', actions[0]!.id), 200)
    return
  }
  timer = setTimeout(() => void command('advance'), 450)
}
function update(s: Snapshot) { clearHint(); room.value = s; selected.value = -1; schedule() }
function fail(e: unknown) { error.value = e instanceof Error ? e.message : '连接失败，请重试'; clearTimeout(timer) }
async function load() {
  busy.value = true; error.value = ''
  try {
    catalog.value = await request<Catalog>('/catalog')
    const saved = sessionStorage.getItem('mahjong-room')
    if (saved) {
      const data = JSON.parse(saved); token = data.token
      try { update(await request<Snapshot>('/rooms/' + data.id, token)) }
      catch (e) { if (e instanceof ApiError && [403,404].includes(e.status)) {sessionStorage.removeItem('mahjong-room'); room.value = null; token = ''} else throw e }
    }
  } catch(e) { fail(e) } finally { busy.value = false }
}
async function start() {
  busy.value = true; error.value = ''; ready.value = false; sceneError.value = ''; showResult.value = true
  try {
    const data = await request<{token: string; snapshot: Snapshot}>('/rooms', '', {rule_id: catalog.value!.defaultRule, difficulties: difficulties.value})
    token = data.token; sessionStorage.setItem('mahjong-room', JSON.stringify({id: data.snapshot.id, token})); update(data.snapshot)
  } catch(e) {fail(e)} finally {busy.value = false}
}
async function command(operation: 'action' | 'advance' | 'next', action_id?: number) {
  if (busy.value || !room.value) return
  clearHint()
  busy.value = true; error.value = ''; clearTimeout(timer)
  try {
    const data = await request<Snapshot>(`/rooms/${room.value.id}/${operation}`, token, {revision: room.value.revision, action_id})
    if (operation === 'next') showResult.value = true
    update(data)
  } catch(e) {fail(e)} finally {busy.value = false}
}
async function openReplay() {
  if (busy.value || !room.value) return
  clearHint()
  busy.value = true; clearTimeout(timer); error.value = ''
  try {replay.value = await request<Replay>(`/rooms/${room.value.id}/replay`, token)}
  catch(e) {fail(e)} finally {busy.value = false}
}
function closeReplay() {replay.value = null; schedule()}
async function retry() {
  if (!room.value) return load()
  busy.value = true; error.value = ''
  try {update(await request<Snapshot>('/rooms/' + room.value.id, token))} catch(e) {fail(e)} finally {busy.value = false}
}
async function leave() {
  if (!room.value || busy.value) return
  if (!room.value.finished && !window.confirm('离开会结束这张牌桌，确定返回大厅吗？')) return
  clearHint()
  busy.value = true; clearTimeout(timer)
  try {
    await request('/rooms/' + room.value.id, token, undefined, 'DELETE')
    room.value = null; token = ''; error.value = ''; sessionStorage.removeItem('mahjong-room')
  } catch(e) {fail(e)} finally {busy.value = false}
}
function choose(index: number) {
  if (!ownTurn.value || busy.value) return
  if (selected.value === index && discard.value) void command('action', discard.value.id)
  else selected.value = index
}
onMounted(load)
onBeforeUnmount(() => {disposed = true; clearHint(); clearTimeout(timer)})
</script>

<template>
  <main class="arena" :class="{'in-game': room}">
    <header class="topbar">
      <a class="brand" href="#" @click.prevent="room ? leave() : undefined"><span class="seal">杭</span><span>杭州麻将<small>在牌桌，见高下</small></span></a>
      <div class="top-actions"><span class="tag">{{ rule?.name ?? '杭州麻将' }}</span><button class="quiet" :aria-expanded="showRules" aria-controls="rules-help" @click="showRules = !showRules">玩法说明</button><button v-if="room" class="quiet" :disabled="busy" @click="leave">离开牌桌</button></div>
    </header>
    <RulesPanel v-if="showRules" :rule="rule" @close="showRules = false"/>
    <div v-if="error" class="error-banner" role="alert">{{ error }} <button :disabled="busy" @click="retry">重新连接</button></div>
    <section v-if="!room" class="lobby">
      <div class="intro"><span class="eyebrow">一人入座 · 三位 AI 同台</span><h1>开一桌，<br>打得尽兴。</h1><p>白板作财，赢家接庄。<br>给每位对手挑一个难度，开始你的杭州牌局。</p><div class="tile-art" aria-hidden="true"><MahjongTile tile="s8" disabled/><MahjongTile tile="white" disabled/><MahjongTile tile="m8" disabled/></div><span class="intro-note">真实模型决策 · 3D 牌桌</span></div>
      <div class="setup"><div class="section-heading"><span>01 / 配置牌桌</span><span class="online-dot">单人练习</span></div><h2>这局，和谁过招？</h2><p class="muted">三位对手的难度可以分别设置。</p>
        <div v-for="(difficulty, i) in difficulties" :key="i" class="opponent"><div class="avatar">{{ seats[i+1]?.slice(0,1) }}</div><div class="opponent-content"><div class="opponent-title"><strong>{{ seats[i+1] }} AI</strong><label :for="'difficulty-'+i" class="sr-only">{{ seats[i+1] }}难度</label><select :id="'difficulty-'+i" v-model="difficulties[i]" :disabled="busy"><option v-for="d in catalog?.difficulties" :value="d.id" :key="d.id">{{ d.name }}</option></select></div><small>{{ catalog?.difficulties.find(d => d.id === difficulty)?.strategy ?? '加载策略…' }}</small></div></div>
        <button class="primary start" :disabled="busy || !catalog" @click="start">{{ busy ? '正在准备牌桌…' : '入座开局' }}<span>→</span></button><p class="setup-note">难度为策略预设 · 积分仅用于本桌练习</p>
      </div>
    </section>
    <section v-else class="play-area">
      <div class="round-bar"><button v-if="room.replayRound && !room.finished" class="quiet" :disabled="busy" @click="openReplay">复盘上一局</button><span>第 {{ room.round }} 局</span><span>庄家 · {{ seats[room.dealer] }}</span><span>可摸 {{ room.drawable }} 张</span></div>
      <div class="scene">
        <TableViewport :key="sceneKey" :camera-scale="1.16" joker-label="财" :players="room.players" :current-player="room.currentPlayer" :last-discard="room.lastDiscard" :wall="wall" :wall-count="room.wallCount" :wall-head-drawn="room.wallHeadDrawn" :dealer-index="room.dealer" :reveal-hands="room.finished" :joker-tiles="['white']" @ready="ready=true" @load-error="sceneError=$event"/>
        <div v-if="sceneError" class="scene-notice" role="alert">3D 牌桌加载失败：{{ sceneError }} <button @click="sceneError=''; ready=false; sceneKey++">重试</button></div>
        <div v-else-if="!ready" class="scene-notice">正在布置 3D 牌桌…</div>
        <div v-for="(player,i) in room.players.slice(1)" :key="player.seat" class="seat-card" :class="['seat-'+(i+1),{active: room.currentPlayer===player.seat}]" :title="player.strategy"><span class="seat-icon">{{ seats[player.seat]?.slice(0,1) }}</span><div><strong>{{ player.name }} <b v-if="room.dealer===player.seat" class="dealer">庄</b></strong><small>{{ player.strategy }}</small><span class="score">{{ signed(player.score) }} 分</span></div></div>
        <AdvicePanel v-if="hint && !room.finished" class="desktop-advice" :recommendation="recommended.label" :probability="recommended.probability" :text="adviceText" :loading="adviceLoading" :error="adviceError"/>
      </div>
      <AdvicePanel v-if="hint && !room.finished" class="mobile-advice" :recommendation="recommended.label" :probability="recommended.probability" :text="adviceText" :loading="adviceLoading" :error="adviceError"/>
      <div class="hand-area"><div class="hand-toolbar"><span><strong>你</strong> <b v-if="room.dealer===0" class="dealer">庄</b> <span class="muted">{{ signed(room.players[0]?.score ?? 0) }} 分</span></span><span class="turn-status" role="status">{{ status }}</span><span v-if="room.finished && !showResult"><button class="quiet" :disabled="busy" @click="openReplay">明牌复盘</button><button class="quiet" @click="showResult=true">查看结算</button></span><span v-else class="hint">{{ choices.length ? "请选择操作" : "选牌后点击出牌" }}</span></div>
        <div v-if="!room.finished" class="ai-hint-toolbar"><label for="hint-difficulty">提示 AI</label><select id="hint-difficulty" v-model="hintDifficulty" :disabled="busy"><option v-for="d in catalog?.hintStrategies" :value="d.id" :key="d.id" :title="d.strategy">{{ d.name }}</option></select><button class="action" :disabled="busy || !ownTurn || adviceLoading" @click="requestHint">{{ hintLoading ? '正在分析…' : 'AI 提示' }}</button><span v-if="hint" class="hint-note">合法动作概率分数；同牌共享分数</span><span v-if="hintError" role="alert" class="hint-error">{{ hintError }}</span></div>
        <div class="hand-rack"><div v-for="(tile,i) in hand" :key="i" class="hand-tile" :class="{'drawn-column':room.players[0]?.drawnTileIndex===i}"><MahjongTile :tile="tile" :selected="selected===i" :drawn="room.players[0]?.drawnTileIndex===i" :disabled="busy || !ownTurn || !room.legalActions.some(a=>a.kind==='discard' && a.tile===tile)" :joker-tiles="['white']" joker-label="财" @choose="choose(i)"/><span v-if="hint" class="tile-probability" :class="{'recommended':selected===i}">{{ tileScore(tile) }}</span></div></div>
        <div class="action-row"><button v-for="action in choices" :key="action.id" :class="[action.kind==='hu' ? 'primary' : 'action', {'suggested':hint && bestHintAction===action.id}]" :disabled="busy" @click="command('action',action.id)"><span v-for="(part,i) in action.labelParts" :key="i" :class="{'claimed-tile':part.claimed}" :title="part.claimed ? '被吃的牌' : undefined">{{ part.text }}</span><small v-if="hint" class="action-probability">{{ score(action.id) }}</small></button><button v-if="ownTurn && room.legalActions.some(a=>a.kind==='discard')" class="primary" :disabled="busy || !discard" @click="discard && command('action',discard.id)">出牌</button><span v-if="!ownTurn && !room.finished" class="muted">AI 正在决策，请稍候</span></div>
      </div>
      <div v-if="room.finished && showResult" class="modal-backdrop"><section class="result-card" role="dialog" aria-modal="true" aria-labelledby="result-title"><span class="eyebrow">第 {{ room.round }} 局 · 结算</span><h2 id="result-title">{{ room.result?.draw ? '流局' : (seats[room.result?.winner ?? 0] + '自摸') }}</h2><p>{{ room.result?.detail?.join(' · ') }}{{ room.result?.fan ? ` · ${room.result.fan} 番` : '' }}</p><div v-for="p in room.players" :key="p.seat" class="result-row"><span>{{ seats[p.seat] }} · {{ p.name }}</span><strong :class="{'positive':(room.result?.scores[p.seat]??0)>0}">{{ signed(room.result?.scores[p.seat]??0) }}</strong></div><p class="muted">下一局由{{ seats[room.result?.next_dealer ?? 0] }}坐庄</p><button class="primary start" :disabled="busy" @click="command('next')">继续下一局 →</button><button class="action replay-open" :disabled="busy" @click="openReplay">明牌复盘本局</button><div class="result-links"><button class="quiet" @click="showResult=false">查看牌桌</button><button class="quiet" :disabled="busy" @click="leave">返回大厅</button></div></section></div>
    </section>
    <ReplayPanel v-if="replay" :replay="replay" @close="closeReplay"/>
  </main>
</template>
