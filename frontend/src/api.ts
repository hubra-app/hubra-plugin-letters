import { apiFetch } from '@hubra/plugin-sdk'

export interface Note {
  id: number
  text: string
  authorId: number | null
  createdAt: string | null
}

export const listNotes = () => apiFetch<Note[]>('/app/example/notes')

export const addNote = (text: string) =>
  apiFetch<Note>('/app/example/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })

export const deleteNote = (id: number) => apiFetch<void>(`/app/example/notes/${id}`, { method: 'DELETE' })
