// Transport-level retry policy for the direct upload flow. Framework free so
// the exact retry behaviour can be unit tested without rendering React.

export type UploadTicket = { token: string; upload_url: string };

export type UploadRetryOptions<Result> = {
  /** Mint a fresh, single-use ticket for one attempt. */
  requestTicket: () => Promise<UploadTicket>;
  /** Send the file with the ticket for this attempt. */
  uploadOnce: (ticket: UploadTicket) => Promise<Result>;
  /** Called at the start of every attempt so progress never carries over. */
  onAttemptStart: () => void;
  /** Called only when a failed upload attempt is about to be retried. */
  onRetry: () => void;
  wait: (milliseconds: number) => Promise<void>;
};

export const MAX_UPLOAD_ATTEMPTS = 2;
export const RETRY_DELAY_MS = 1200;

// Only transport-level failures are retried. A server decision such as
// 401/413/415/422 must never be resubmitted.
const RETRYABLE_FAILURE = /interrupted|timed out|could not be reached|unavailable/i;

function isRetryable(error: unknown): boolean {
  return error instanceof Error && RETRYABLE_FAILURE.test(error.message);
}

export async function uploadWithRetry<Result>(
  options: UploadRetryOptions<Result>,
): Promise<Result> {
  let lastError: unknown = null;

  for (let attempt = 0; attempt < MAX_UPLOAD_ATTEMPTS; attempt += 1) {
    // Reset progress at the beginning of every attempt, including a retry, so
    // the second attempt never inherits the aborted attempt's percentage.
    options.onAttemptStart();

    // A ticket is single-use, so every attempt (including a retry) mints a
    // fresh one. This also prevents replaying a consumed ticket.
    let ticket: UploadTicket;
    try {
      ticket = await options.requestTicket();
    } catch (error) {
      lastError = error;
      if (attempt === MAX_UPLOAD_ATTEMPTS - 1 || !isRetryable(error)) throw error;
      await options.wait(RETRY_DELAY_MS);
      continue;
    }

    try {
      return await options.uploadOnce(ticket);
    } catch (error) {
      lastError = error;
      if (attempt === MAX_UPLOAD_ATTEMPTS - 1 || !isRetryable(error)) throw error;
      options.onRetry();
      await options.wait(RETRY_DELAY_MS);
    }
  }

  throw lastError instanceof Error ? lastError : new Error("The upload could not be completed.");
}
