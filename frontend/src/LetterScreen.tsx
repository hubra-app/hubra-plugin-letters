import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Anchor,
  Badge,
  Button,
  CloseButton,
  Group,
  Menu,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core'
import {
  IconArrowLeft,
  IconDots,
  IconDownload,
  IconMailForward,
  IconPrinter,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-react'
import {
  ConfirmModal,
  ErrorBanner,
  Field,
  LoadingSpinner,
  MemberPicker,
  PageHead,
  Seg,
  formatDateTime,
  useT,
  useToast,
} from '@hubra/plugin-sdk'
import {
  AUDIENCES,
  QK,
  buildAll,
  deleteLetter,
  downloadAll,
  errorText,
  getLetter,
  getOptions,
  markPrinted,
  previewUrl,
  retryFailed,
  saveLetter,
  sendByPost,
  type Draft,
  type ItemStatus,
  type LetterDetail,
  type Options,
} from './api'
import { StatusBadge } from './LettersScreen'

const PLACEHOLDERS = ['{vorname}', '{nachname}', '{name}']
const EMPTY: Draft = { subject: '', body: '', audience: 'no_email', groupId: null, memberIds: [] }

/** Runs an action with a busy flag and a toast for errors. */
function useAction() {
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    try {
      await fn()
      if (ok) notify('success', ok)
      return true
    } catch (err) {
      notify('error', errorText(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, run }
}

export function LetterScreen() {
  const { t } = useT()
  const navigate = useNavigate()
  const { id: raw } = useParams()
  const id = raw ? Number(raw) : undefined
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const letter = useQuery({
    queryKey: QK.letter(id ?? 0),
    queryFn: () => getLetter(id!),
    enabled: !!id,
    // While Pingen posts the letters or the PDF is built, the state changes by itself.
    refetchInterval: (q) =>
      q.state.data?.pdf?.status === 'building' ? 3_000 : q.state.data?.status === 'sending' ? 15_000 : false,
  })

  const err = options.error || letter.error
  if (err) return <ErrorBanner message={errorText(err)} onRetry={() => (options.refetch(), letter.refetch())} />
  if (options.isLoading || (id && letter.isLoading) || !options.data) return <LoadingSpinner />
  const l = letter.data

  return (
    <>
      <PageHead
        title={l ? l.subject : t('letters.new')}
        desc={
          <Anchor size="sm" onClick={() => navigate('/app/letters')}>
            <IconArrowLeft size={14} /> {t('letters.title')}
          </Anchor>
        }
        actions={l ? <StatusBadge status={l.status} /> : undefined}
      />
      {!l || l.status === 'draft' ? (
        <Editor key={l?.id ?? 'new'} letter={l} options={options.data} />
      ) : (
        <Sent letter={l} />
      )}
    </>
  )
}

// ── Writing ──────────────────────────────────────────────────────────────────

function Editor({ letter, options }: { letter?: LetterDetail; options: Options }) {
  const { t } = useT()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { busy, run } = useAction()
  const [draft, setDraft] = useState<Draft>(
    letter
      ? {
          subject: letter.subject,
          body: letter.body,
          audience: letter.audience,
          groupId: letter.groupId,
          memberIds: letter.memberIds,
        }
      : EMPTY,
  )
  const [picked, setPicked] = useState<Record<number, string>>(() =>
    Object.fromEntries([...(letter?.recipients ?? []), ...(letter?.missing ?? [])].map((r) => [r.memberId, r.name])),
  )
  const [confirm, setConfirm] = useState<null | 'printed' | 'send' | 'delete'>(null)
  const body = useRef<HTMLTextAreaElement>(null)
  const saved =
    !!letter &&
    letter.subject === draft.subject &&
    letter.body === draft.body &&
    letter.audience === draft.audience &&
    (letter.groupId ?? null) === draft.groupId &&
    letter.memberIds.join() === [...draft.memberIds].sort((a, b) => a - b).join()
  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))

  const insert = (token: string) => {
    const el = body.current
    const at = el ? el.selectionStart : draft.body.length
    const end = el ? el.selectionEnd : at
    set({ body: draft.body.slice(0, at) + token + draft.body.slice(end) })
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(at + token.length, at + token.length)
    })
  }

  const save = () =>
    run(async () => {
      const out = await saveLetter(draft, letter?.id)
      qc.setQueryData(QK.letter(out.id), out)
      qc.invalidateQueries({ queryKey: QK.list })
      if (!letter) navigate(`/app/letters/${out.id}`, { replace: true })
    }, t('letters.saved'))

  const act = async (fn: (id: number) => Promise<LetterDetail>, ok: string) => {
    setConfirm(null)
    await run(async () => {
      const out = await fn(letter!.id)
      qc.setQueryData(QK.letter(out.id), out)
      qc.invalidateQueries({ queryKey: QK.list })
    }, ok)
  }

  const recipients = letter?.recipients ?? []
  const missing = letter?.missing ?? []

  return (
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
      <Stack gap="md">
        <Field label={t('letters.subject')}>
          <TextInput value={draft.subject} maxLength={200} onChange={(e) => set({ subject: e.currentTarget.value })} />
        </Field>
        <Field label={t('letters.body')}>
          <Textarea
            ref={body}
            value={draft.body}
            autosize
            minRows={10}
            maxLength={20000}
            placeholder={t('letters.bodyHint')}
            onChange={(e) => set({ body: e.currentTarget.value })}
          />
          <Group gap={6} mt={6}>
            <Text size="xs" c="dimmed">
              {t('letters.insert')}
            </Text>
            {PLACEHOLDERS.map((p) => (
              <Badge
                key={p}
                size="sm"
                variant="outline"
                color="gray"
                style={{ textTransform: 'none', cursor: 'pointer' }}
                onClick={() => insert(p)}
              >
                {p}
              </Badge>
            ))}
            <Text size="xs" c="dimmed">
              {t('letters.boldHint')}
            </Text>
          </Group>
        </Field>
        <Field label={t('letters.to')}>
          <Seg
            value={draft.audience}
            onChange={(v) => set({ audience: v as Draft['audience'] })}
            options={AUDIENCES.map((a) => ({ value: a, label: t(`letters.audience.${a}`) }))}
          />
          <Text size="xs" c="dimmed" mt={6}>
            {t(`letters.audienceHint.${draft.audience}`)}
          </Text>
        </Field>
        {draft.audience === 'group' && (
          <Select
            label={t('letters.group')}
            data={options.groups.map((g) => ({ value: String(g.id), label: g.name }))}
            value={draft.groupId ? String(draft.groupId) : null}
            onChange={(v) => set({ groupId: v ? Number(v) : null })}
            searchable
          />
        )}
        {draft.audience === 'picked' && (
          <Stack gap={6}>
            <MemberPicker
              label={t('letters.addMember')}
              value={null}
              onChange={(mid, m) => {
                if (!mid) return
                const n = Number(mid)
                if (!draft.memberIds.includes(n)) set({ memberIds: [...draft.memberIds, n] })
                setPicked((p) => ({ ...p, [n]: m?.name ?? `#${n}` }))
              }}
            />
            <Group gap={6}>
              {draft.memberIds.map((n) => (
                <Badge
                  key={n}
                  variant="light"
                  color="gray"
                  style={{ textTransform: 'none' }}
                  rightSection={
                    <CloseButton
                      size="xs"
                      aria-label={t('letters.remove')}
                      onClick={() => set({ memberIds: draft.memberIds.filter((x) => x !== n) })}
                    />
                  }
                >
                  {picked[n] ?? `#${n}`}
                </Badge>
              ))}
            </Group>
          </Stack>
        )}
        <Group justify="space-between">
          <Button onClick={save} loading={busy} disabled={saved || !draft.subject.trim() || !draft.body.trim()}>
            {letter ? t('letters.save') : t('letters.create')}
          </Button>
          {letter && (
            <Menu position="bottom-end">
              <Menu.Target>
                <Button variant="default" leftSection={<IconDots size={16} />}>
                  {t('letters.more')}
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item color="red" leftSection={<IconTrash size={14} />} onClick={() => setConfirm('delete')}>
                  {t('letters.delete')}
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          )}
        </Group>
      </Stack>

      <Stack gap="md">
        {!letter ? (
          <Paper withBorder radius="md" p="md">
            <Text size="sm" c="dimmed">
              {t('letters.saveFirst')}
            </Text>
          </Paper>
        ) : (
          <>
            <Paper withBorder radius="md" p="md">
              <Text fw={700} mb={4}>
                {t('letters.recipients', { count: recipients.length })}
              </Text>
              {!saved && (
                <Text size="xs" c="orange" mb={6}>
                  {t('letters.unsaved')}
                </Text>
              )}
              {missing.length > 0 && (
                <Alert color="orange" variant="light" p="xs" mb="xs">
                  <Text size="sm">
                    {t('letters.missing', { count: missing.length })} {missing.map((m) => m.name).join(', ')}
                  </Text>
                </Alert>
              )}
              <Text size="sm" c="dimmed" lineClamp={3}>
                {recipients.map((r) => r.name).join(', ') || t('letters.nobody')}
              </Text>
              <Group gap="xs" mt="md">
                {letter.pdf?.status === 'ready' ? (
                  <Button
                    variant="default"
                    leftSection={<IconDownload size={16} />}
                    disabled={!saved}
                    onClick={() => run(() => downloadAll(letter.id, letter.subject))}
                  >
                    {t('letters.download', { count: letter.pdf.count ?? 0 })}
                  </Button>
                ) : (
                  <Button
                    variant="default"
                    leftSection={<IconDownload size={16} />}
                    loading={letter.pdf?.status === 'building'}
                    disabled={!recipients.length || !saved}
                    onClick={() => act(buildAll, t('letters.buildToast'))}
                  >
                    {t('letters.build')}
                  </Button>
                )}
                <Button
                  variant="default"
                  leftSection={<IconPrinter size={16} />}
                  disabled={!recipients.length || !saved}
                  onClick={() => setConfirm('printed')}
                >
                  {t('letters.markPrinted')}
                </Button>
                <Button
                  leftSection={<IconMailForward size={16} />}
                  disabled={!recipients.length || !saved || !options.pingen}
                  onClick={() => setConfirm('send')}
                >
                  {t('letters.send')}
                </Button>
              </Group>
              {letter.pdf?.status === 'building' && (
                <Text size="xs" c="dimmed" mt={6}>
                  {t('letters.building')}
                </Text>
              )}
              {letter.pdf?.status === 'ready' && (
                <Text size="xs" c="dimmed" mt={6}>
                  {t('letters.builtAt', { when: formatDateTime(letter.pdf.at ?? '') })}{' '}
                  <Anchor size="xs" onClick={() => act(buildAll, t('letters.buildToast'))}>
                    {t('letters.rebuild')}
                  </Anchor>
                </Text>
              )}
              {letter.pdf?.status === 'failed' && (
                <Text size="xs" c="red" mt={6}>
                  {letter.pdf.error}
                </Text>
              )}
              {!options.pingen && (
                <Text size="xs" c="dimmed" mt={6}>
                  {t('letters.pingenHint')}
                </Text>
              )}
            </Paper>
            <Preview letter={letter} stamp={letter.updatedAt ?? ''} />
          </>
        )}
      </Stack>

      <ConfirmModal
        open={confirm === 'send'}
        title={t('letters.sendTitle', { count: recipients.length })}
        body={t('letters.sendBody')}
        confirmLabel={t('letters.send')}
        onClose={() => setConfirm(null)}
        onConfirm={() => act(sendByPost, t('letters.sentToast'))}
      />
      <ConfirmModal
        open={confirm === 'printed'}
        title={t('letters.printedTitle')}
        body={t('letters.printedBody', { count: recipients.length })}
        confirmLabel={t('letters.markPrinted')}
        onClose={() => setConfirm(null)}
        onConfirm={() => act(markPrinted, t('letters.printedToast'))}
      />
      <ConfirmModal
        open={confirm === 'delete'}
        title={t('letters.deleteTitle')}
        body={t('letters.deleteBody')}
        confirmLabel={t('letters.delete')}
        onClose={() => setConfirm(null)}
        onConfirm={async () => {
          setConfirm(null)
          if (await run(() => deleteLetter(letter!.id))) {
            qc.invalidateQueries({ queryKey: QK.list })
            navigate('/app/letters')
          }
        }}
      />
    </SimpleGrid>
  )
}

/** The letter as the first recipient (or a chosen one) gets it. */
function Preview({ letter, stamp }: { letter: LetterDetail; stamp: string }) {
  const { t } = useT()
  const [who, setWho] = useState<string | null>(null)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let made: string | null = null
    let live = true
    previewUrl(letter.id, who ? Number(who) : undefined)
      .then((u) => {
        made = u
        if (live) (setUrl(u), setError(null))
        else URL.revokeObjectURL(u)
      })
      .catch((e) => live && setError(errorText(e)))
    return () => {
      live = false
      if (made) URL.revokeObjectURL(made)
    }
  }, [letter.id, who, stamp, tick])

  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="xs" wrap="nowrap">
        <Text fw={700}>{t('letters.preview')}</Text>
        <Group gap={6} wrap="nowrap">
          {(letter.recipients?.length ?? 0) > 1 && (
            <Select
              size="xs"
              w={180}
              placeholder={letter.recipients![0].name}
              data={letter.recipients!.map((r) => ({ value: String(r.memberId), label: r.name }))}
              value={who}
              onChange={setWho}
              searchable
            />
          )}
          <Button size="xs" variant="subtle" leftSection={<IconRefresh size={14} />} onClick={() => setTick((n) => n + 1)}>
            {t('letters.refresh')}
          </Button>
        </Group>
      </Group>
      {error ? (
        <Text size="sm" c="red">
          {error}
        </Text>
      ) : url ? (
        <iframe
          title={t('letters.preview')}
          src={url}
          style={{ width: '100%', aspectRatio: '210 / 297', border: '1px solid var(--hb-border, #ddd)', borderRadius: 6 }}
        />
      ) : (
        <LoadingSpinner />
      )}
    </Paper>
  )
}

// ── After sending ────────────────────────────────────────────────────────────

const ITEM_COLORS: Record<ItemStatus, string> = { queued: 'blue', sent: 'green', failed: 'red', printed: 'green' }

function Sent({ letter }: { letter: LetterDetail }) {
  const { t } = useT()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { busy, run } = useAction()
  const [deleting, setDeleting] = useState(false)
  const items = letter.sent ?? []
  const failed = items.filter((i) => i.status === 'failed').length

  return (
    <Stack gap="md">
      <Paper withBorder radius="md" p="md">
        <Text size="sm" c="dimmed" mb="xs">
          {t(letter.status === 'printed' ? 'letters.printedOn' : 'letters.postedOn', {
            when: formatDateTime(letter.sentAt ?? ''),
            count: items.length,
          })}
        </Text>
        <Text fw={700} mb={4}>
          {letter.subject}
        </Text>
        <Text size="sm" style={{ whiteSpace: 'pre-wrap' }} lineClamp={6}>
          {letter.body}
        </Text>
      </Paper>
      {failed > 0 && (
        <Alert color="red" variant="light">
          <Group justify="space-between">
            <Text size="sm">{t('letters.failedHint', { count: failed })}</Text>
            <Button
              size="xs"
              loading={busy}
              onClick={() =>
                run(async () => {
                  qc.setQueryData(QK.letter(letter.id), await retryFailed(letter.id))
                  qc.invalidateQueries({ queryKey: QK.list })
                }, t('letters.retried'))
              }
            >
              {t('letters.retry')}
            </Button>
          </Group>
        </Alert>
      )}
      <Paper withBorder radius="md" p={0} style={{ overflowX: 'auto' }}>
        <Table verticalSpacing="xs" horizontalSpacing="md">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('letters.recipient')}</Table.Th>
              <Table.Th>{t('letters.address')}</Table.Th>
              <Table.Th>{t('letters.state')}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((i) => (
              <Table.Tr key={i.id}>
                <Table.Td>{i.name}</Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {i.address.join(', ')}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Badge size="sm" variant="light" color={ITEM_COLORS[i.status]} style={{ textTransform: 'none' }}>
                    {t(`letters.item.${i.status}`)}
                  </Badge>
                  {i.error && (
                    <Text size="xs" c="red">
                      {i.error}
                    </Text>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>
      {letter.status !== 'sending' && (
        <Group>
          <Button variant="subtle" color="red" leftSection={<IconTrash size={16} />} onClick={() => setDeleting(true)}>
            {t('letters.delete')}
          </Button>
        </Group>
      )}
      <ConfirmModal
        open={deleting}
        title={t('letters.deleteTitle')}
        body={t('letters.deleteSentBody')}
        confirmLabel={t('letters.delete')}
        onClose={() => setDeleting(false)}
        onConfirm={async () => {
          setDeleting(false)
          if (await run(() => deleteLetter(letter.id))) {
            qc.invalidateQueries({ queryKey: QK.list })
            navigate('/app/letters')
          }
        }}
      />
    </Stack>
  )
}
