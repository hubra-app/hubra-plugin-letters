import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Badge, Button, Group, Paper, Stack, Text } from '@mantine/core'
import { IconMailForward, IconPlus } from '@tabler/icons-react'
import { EmptyState, ErrorBanner, LoadingSpinner, PageHead, formatDateTime, useT } from '@hubra/plugin-sdk'
import { QK, errorText, listLetters, type Letter, type Status } from './api'

const COLORS: Record<Status, string> = { draft: 'gray', sending: 'blue', sent: 'green', printed: 'green' }

export function StatusBadge({ status }: { status: Status }) {
  const { t } = useT()
  return (
    <Badge size="sm" variant="light" color={COLORS[status]} style={{ textTransform: 'none', flexShrink: 0 }}>
      {t(`letters.status.${status}`)}
    </Badge>
  )
}

/** Drafts and the letters already printed or posted, newest first. */
export function LettersScreen() {
  const { t } = useT()
  const navigate = useNavigate()
  const letters = useQuery({ queryKey: QK.list, queryFn: listLetters })

  if (letters.error) return <ErrorBanner message={errorText(letters.error)} onRetry={() => letters.refetch()} />
  if (letters.isLoading) return <LoadingSpinner />
  const list = letters.data ?? []

  return (
    <>
      <PageHead
        title={t('letters.title')}
        desc={t('letters.desc')}
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => navigate('/app/letters/new')}>
            {t('letters.new')}
          </Button>
        }
      />
      {!list.length ? (
        <EmptyState icon={<IconMailForward size={28} />} title={t('letters.none')} description={t('letters.noneHint')} />
      ) : (
        <Stack gap="xs">
          {list.map((l) => (
            <Row key={l.id} letter={l} onOpen={() => navigate(`/app/letters/${l.id}`)} />
          ))}
        </Stack>
      )}
    </>
  )
}

function Row({ letter, onOpen }: { letter: Letter; onOpen: () => void }) {
  const { t } = useT()
  const count = Object.values(letter.items).reduce((a, b) => a + (b ?? 0), 0)
  const failed = letter.items.failed ?? 0
  return (
    <Paper withBorder radius="md" p="md" style={{ cursor: 'pointer' }} onClick={onOpen}>
      <Group justify="space-between" wrap="nowrap" align="flex-start">
        <div style={{ minWidth: 0 }}>
          <Text fw={700} truncate>
            {letter.subject}
          </Text>
          <Text size="sm" c="dimmed">
            {letter.status === 'draft'
              ? t('letters.editedOn', { when: formatDateTime(letter.updatedAt ?? '') })
              : t('letters.sentOn', { when: formatDateTime(letter.sentAt ?? ''), count })}
            {failed > 0 && (
              <Text span c="red" size="sm">
                {' · '}
                {t('letters.failedCount', { count: failed })}
              </Text>
            )}
          </Text>
        </div>
        <StatusBadge status={letter.status} />
      </Group>
    </Paper>
  )
}
