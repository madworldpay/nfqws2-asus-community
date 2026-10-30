/** A failed request may carry an empty/string body, including a normal HTTP 401. */
export const isAuthUnconfigured = (error: unknown): boolean =>
  typeof error === 'object' &&
  error !== null &&
  !Array.isArray(error) &&
  'error' in error &&
  error.error === 'auth_unconfigured';
