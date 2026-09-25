/**
 * Should a failed stream wait for the answer, or report the failure now?
 *
 * A run is detached on the server: it finishes and saves even after the
 * connection that started it has gone. So a broken stream is usually a lost
 * connection, not a lost answer, and the thread should stay locked while the
 * saved row is fetched. Unlocking the composer at that moment is what let one
 * question collect two answers.
 *
 * The opposite mistake is worse for the reader: a request refused BEFORE a run
 * started (not signed in, free questions used up, rate limited) has nothing to
 * wait for, and locking the composer for three minutes over it would strand
 * someone who just needs to sign in.
 */
export function shouldWaitForAnswer(opts: {
  /** The server accepted the run: past auth, the trial gate and the duplicate guard. */
  accepted: boolean
  /** The server refused because this exact question is already being answered. */
  alreadyAnswering: boolean
  /** Recovery reads the thread as the signed-in reader; a guest cannot. */
  signedIn: boolean
}): boolean {
  if (!opts.signedIn) return false
  return opts.accepted || opts.alreadyAnswering
}
