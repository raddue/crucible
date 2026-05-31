/**
 * Retry utility with exponential backoff.
 *
 * Retries a given async function up to `maxRetries` times, waiting an
 * exponentially increasing delay between attempts. An optional jitter
 * factor randomises the delay to avoid thundering-herd problems.
 */

export interface RetryOptions {
  /** Maximum number of retry attempts (default: 3). */
  maxRetries?: number;
  /** Initial delay in milliseconds before the first retry (default: 200). */
  baseDelayMs?: number;
  /** Multiplier applied to the delay after each attempt (default: 2). */
  backoffFactor?: number;
  /** Maximum delay cap in milliseconds (default: 30 000). */
  maxDelayMs?: number;
  /** Jitter factor 0-1 — proportion of the delay that is randomised (default: 0.1). */
  jitter?: number;
  /** Optional predicate — return `false` to abort retries for non-retryable errors. */
  shouldRetry?: (error: unknown) => boolean;
}

export async function retry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const {
    maxRetries = 3,
    baseDelayMs = 200,
    backoffFactor = 2,
    maxDelayMs = 30_000,
    jitter = 0.1,
    shouldRetry = () => true,
  } = options;

  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (attempt === maxRetries || !shouldRetry(error)) {
        break;
      }

      const exponentialDelay = baseDelayMs * backoffFactor ** attempt;
      const capped = Math.min(exponentialDelay, maxDelayMs);
      const jitterAmount = capped * jitter * Math.random();
      const delay = capped + jitterAmount;

      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}
