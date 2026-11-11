import { apiFetch, apiFetchRaw } from '@hubra/plugin-sdk'

export type Audience = 'no_email' | 'all' | 'group' | 'picked'
export const AUDIENCES: Audience[] = ['no_email', 'all', 'group', 'picked']
export type Status = 'draft' | 'sending' | 'sent' | 'printed'
export type ItemStatus = 'queued' | 'sent' | 'failed' | 'printed'

export interface Options {
  window: 'right' | 'left'
  letterhead: { name: string; lines: string[]; city: string }
  pingen: boolean
  groups: { id: number; name: string }[]
}

export interface Letter {
  id: number
  subject: string
  body: string
  audience: Audience
  groupId: number | null
  memberIds: number[]
  status: Status
  sentAt: string | null
  createdBy: string | null
  createdAt: string | null
  updatedAt: string | null
  items: Partial<Record<ItemStatus, number>>
  /** The print PDF of every letter, built in the background. */
  pdf: { status: PdfStatus | null; count: number | null; error: string | null; at: string | null }
}

export type PdfStatus = 'building' | 'ready' | 'failed'

export interface LetterDetail extends Letter {
  recipients?: { memberId: number; name: string; address: string[] }[]
  missing?: { memberId: number; name: string }[]
  sent?: {
    id: number
    memberId: number | null
    name: string
    address: string[]
    status: ItemStatus
    error: string | null
    updatedAt: string | null
  }[]
}

export interface Draft {
  subject: string
  body: string
  audience: Audience
  groupId: number | null
  memberIds: number[]
}

export const QK = {
  all: ['letters'] as const,
  options: ['letters', 'options'] as const,
  list: ['letters', 'list'] as const,
  letter: (id: number) => ['letters', 'letter', id] as const,
}

const BASE = '/app/letters'
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const getOptions = () => apiFetch<Options>(`${BASE}/options`)
export const listLetters = () => apiFetch<Letter[]>(`${BASE}/letters`)
export const getLetter = (id: number) => apiFetch<LetterDetail>(`${BASE}/letters/${id}`)
export const saveLetter = (body: Draft, id?: number) =>
  apiFetch<LetterDetail>(id ? `${BASE}/letters/${id}` : `${BASE}/letters`, json(id ? 'PUT' : 'POST', body))
export const deleteLetter = (id: number) => apiFetch<void>(`${BASE}/letters/${id}`, { method: 'DELETE' })
export const markPrinted = (id: number) => apiFetch<LetterDetail>(`${BASE}/letters/${id}/printed`, json('POST', {}))
export const sendByPost = (id: number) => apiFetch<LetterDetail>(`${BASE}/letters/${id}/send`, json('POST', {}))
/** Starts building the PDF of every letter; the letter's `pdf` tells when it's ready. */
export const buildAll = (id: number) => apiFetch<LetterDetail>(`${BASE}/letters/${id}/letters.pdf`, json('POST', {}))
export const retryFailed = (id: number) => apiFetch<LetterDetail>(`${BASE}/letters/${id}/retry`, json('POST', {}))

async function pdfBlob(path: string) {
  const res = await apiFetchRaw(path)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.message || `HTTP ${res.status}`)
  }
  return res.blob()
}

/** One recipient's letter, as an object URL for the preview frame. */
export async function previewUrl(id: number, memberId?: number) {
  const q = memberId ? `?member=${memberId}` : ''
  return URL.createObjectURL(await pdfBlob(`${BASE}/letters/${id}/preview.pdf${q}`))
}

/** Every letter in one PDF, downloaded. */
export async function downloadAll(id: number, subject: string) {
  const url = URL.createObjectURL(await pdfBlob(`${BASE}/letters/${id}/letters.pdf`))
  const a = document.createElement('a')
  a.href = url
  a.download = `${subject.replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '') || 'letters'}.pdf`
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err)
}
