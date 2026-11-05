import { useState } from 'react'
import { ActionIcon, Button, Card, Group, Stack, Text, Textarea } from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { IconTrash } from '@tabler/icons-react'
import { PageHead, formatDateTime, useAuth, useT, useToast } from '@hubra/plugin-sdk'
import { addNote, deleteNote, listNotes } from './api'

export function NotesScreen() {
  const { t } = useT()
  const { notify } = useToast()
  const { hasPermission } = useAuth()
  const queryClient = useQueryClient()
  const canWrite = hasPermission('example.notes.write')
  const [text, setText] = useState('')
  const { data: notes = [], isLoading } = useQuery({ queryKey: ['example-notes'], queryFn: listNotes })

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['example-notes'] })

  const save = async () => {
    try {
      await addNote(text)
      setText('')
      notify('success', t('example.saved'))
      refresh()
    } catch (err) {
      notify('error', err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <>
      <PageHead title={t('example.title')} desc={t('example.desc')} />
      <Stack gap="md" maw={720}>
        {canWrite && (
          <Card withBorder>
            <Stack gap="sm">
              <Textarea
                autosize
                minRows={2}
                placeholder={t('example.placeholder')}
                value={text}
                onChange={(e) => setText(e.currentTarget.value)}
              />
              <Group justify="flex-end">
                <Button onClick={save} disabled={!text.trim()}>
                  {t('example.add')}
                </Button>
              </Group>
            </Stack>
          </Card>
        )}
        {isLoading ? (
          <Text c="dimmed">{t('example.loading')}</Text>
        ) : notes.length === 0 ? (
          <Text c="dimmed">{t('example.empty')}</Text>
        ) : (
          notes.map((n) => (
            <Card key={n.id} withBorder>
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Stack gap={4}>
                  <Text style={{ whiteSpace: 'pre-wrap' }}>{n.text}</Text>
                  {n.createdAt && (
                    <Text size="xs" c="dimmed">
                      {formatDateTime(n.createdAt)}
                    </Text>
                  )}
                </Stack>
                {canWrite && (
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    aria-label={t('example.delete')}
                    onClick={async () => {
                      await deleteNote(n.id)
                      refresh()
                    }}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                )}
              </Group>
            </Card>
          ))
        )}
      </Stack>
    </>
  )
}
