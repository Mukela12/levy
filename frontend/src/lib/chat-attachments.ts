/**
 * What a new message tells the model about documents attached earlier.
 *
 * A document belongs to the message it was attached to: its chip sits there,
 * and the composer is cleared for the next message, because session-wide
 * attachment made chips bleed into every later turn. But the model saw a
 * document only on that one turn, and the history sent with later messages is
 * text alone. On 23 October 2026 a user's next message said they had attached
 * a PDF; that request carried no attachment and its history no trace of one,
 * so Levy said it could not see it and opened a document of its own instead. Now the history names each message's
 * attachments, and the next few messages send the latest ones again.
 */

export type AttachedDoc = { id: string; title: string }

type ChatTurn = { role: string; content: string; blocks?: ReadonlyArray<unknown> | null }

/** How many later messages still carry the most recent attachments. */
export const CARRY_TURNS = 3

/** The documents attached to one message (its `attachments` block). */
export function attachedDocsOf(turn: ChatTurn): AttachedDoc[] {
  for (const raw of turn.blocks ?? []) {
    const block = raw as { kind?: unknown; docs?: unknown } | null
    if (!block || block.kind !== 'attachments' || !Array.isArray(block.docs)) continue
    return block.docs
      .filter((d): d is { id: string; title?: unknown } => !!d && typeof d.id === 'string' && d.id !== '')
      .map((d) => ({ id: d.id, title: typeof d.title === 'string' && d.title.trim() ? d.title.trim() : 'Document' }))
  }
  return []
}

/**
 * The conversation as it is sent with a new message: text only, but a user
 * message that carried documents says so, with their ids, so the model can
 * open one when the user refers back to it.
 */
export function historyFor(turns: ReadonlyArray<ChatTurn>): Array<{ role: string; content: string }> {
  return turns
    .filter((t) => t.content)
    .map((t) => {
      const docs = t.role === 'user' ? attachedDocsOf(t) : []
      if (docs.length === 0) return { role: t.role, content: t.content }
      const names = docs.map((d) => `"${d.title}" (document_id ${d.id})`).join('; ')
      return { role: t.role, content: `${t.content}\n\n[Attached to this message: ${names}]` }
    })
}

/**
 * The documents a new message carries from an earlier one: those on the most
 * recent user message that had any, while it is one of the last `turns` user
 * messages. None when the new message brings documents of its own.
 */
export function earlierAttachments(
  turns: ReadonlyArray<ChatTurn>,
  attachingNow: number,
  carry: number = CARRY_TURNS,
): AttachedDoc[] {
  if (attachingNow > 0) return []
  const users = turns.filter((t) => t.role === 'user')
  for (let back = 0; back < carry && back < users.length; back++) {
    const docs = attachedDocsOf(users[users.length - 1 - back])
    if (docs.length > 0) return docs
  }
  return []
}
