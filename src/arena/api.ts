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

export interface Replay {
  round: number
  frames: {index: number; label: string; events: string[]; snapshot: Snapshot}[]
}
