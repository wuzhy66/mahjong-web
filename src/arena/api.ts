import type { GamePlayer, TileType } from '../game/core/contracts/types'
export interface Catalog {
  defaultRule: string
  rules: {id: string; name: string; description: string}[]
  difficulties: {id: string; name: string; strategy: string}[]
  hintStrategies: {id: string; name: string; strategy: string}[]
}
export interface Snapshot {
  id: string; ruleId: string; revision: number; round: number; dealer: number; currentPlayer: number
  players: (GamePlayer & {strategy: string})[]
  legalActions: {id: number; kind: string; label: string; tile: TileType | null}[]
  replayRound?: number | null
  finished: boolean
  result: {draw: boolean; winner?: number; fan?: number; scores: number[]; detail?: string[]; next_dealer: number} | null
  wallCount: number; drawable: number; wallHeadDrawn: number
  lastDiscard: {id: number; tile: TileType; from: number} | null
}
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}
export async function request<T>(path: string, token = '', body?: unknown, method?: string): Promise<T> {
  const response = await fetch('/api' + path, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: {'Content-Type': 'application/json', 'x-room-token': token},
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(60000),
  })
  const data = await response.json()
  if (!response.ok) throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : '请求无效，请重试')
  return data as T
}

export interface Hint {
  revision: number
  difficulty: string
  actions: {id: number; probability: number}[]
}

export type HintEvent = {type: 'hint'; data: Hint} | {type: 'delta'; data: {text: string}}
  | {type: 'error'; data: {message: string}} | {type: 'done'; data: Record<string, never>}

export async function streamHint(path: string, token: string, body: {revision: number; difficulty: string},
                                 signal: AbortSignal, receive: (event: HintEvent) => void) {
  const response = await fetch('/api' + path, {
    method: 'POST', headers: {'Content-Type': 'application/json', 'x-room-token': token},
    body: JSON.stringify(body), signal: AbortSignal.any([signal, AbortSignal.timeout(100000)]),
  })
  if (!response.ok) {
    const data = await response.json()
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'AI 提示请求失败')
  }
  if (!response.body) throw new Error('浏览器不支持流式建议')
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', kind = '', data: string[] = [], finished = false
  function line(value: string) {
    if (!value) {
      if (data.length && ['hint', 'delta', 'error', 'done'].includes(kind)) {
        receive({type: kind, data: JSON.parse(data.join('\n'))} as HintEvent)
        if (kind === 'done' || kind === 'error') finished = true
      }
      kind = ''; data = []; return
    }
    if (value.startsWith('event:')) kind = value.slice(6).trim()
    else if (value.startsWith('data:')) data.push(value.slice(5).trimStart())
  }
  try {
    while (!finished) {
      const part = await reader.read()
      buffer += decoder.decode(part.value, {stream: !part.done})
      let newline: number
      while ((newline = buffer.indexOf('\n')) >= 0) {
        line(buffer.slice(0, newline).replace(/\r$/, ''))
        buffer = buffer.slice(newline + 1)
      }
      if (part.done) break
    }
    if (!finished) throw new Error('AI 建议连接中断，请重试')
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}

export interface Replay {
  round: number
  frames: {index: number; label: string; events: string[]; snapshot: Snapshot}[]
}
