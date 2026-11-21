/**
 * Whether the tour opens by itself when a page settles.
 *
 * Only for someone who has signed in and has not seen it. A visitor who has
 * not signed in came to ask one thing, and the tour stood between them and
 * the message box: it dims the whole page and covers the lower half of a
 * phone. Four ads sent 256 people to Levy on 20 and 21 November 2026; 3 of
 * them asked a question. The tour explains files, matters and notes, which
 * need an account, so it waits for the account. Profile can replay it.
 */
export interface TourVisit {
  signedIn: boolean
  /** The account records that the tour was finished or skipped. */
  seenOnAccount: boolean
  /** This browser records the same. */
  seenInBrowser: boolean
  /** The chat screen, where the tour starts. */
  onChat: boolean
  /** In the app, the AI-services consent comes before anything else. */
  awaitingConsent: boolean
}

export function tourOpensUnasked(visit: TourVisit): boolean {
  if (!visit.signedIn) return false
  if (visit.seenOnAccount || visit.seenInBrowser) return false
  if (visit.awaitingConsent) return false
  return visit.onChat
}
