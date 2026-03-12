/**
 * Criteria identifiers for password strength validation.
 */
export type PasswordCriterion = 'minLength' | 'uppercase' | 'lowercase' | 'digit' | 'specialChar';

/**
 * Result of a password strength validation.
 *
 * @property score    - Number of scored criteria met (0-4).
 *                      The four scored groups are: minLength, letter case
 *                      (upper + lower combined), digit, and specialChar.
 * @property failures - List of individual criteria that were NOT met.
 */
export interface PasswordStrengthResult {
  score: number;
  failures: PasswordCriterion[];
}

/**
 * Validates password strength against these checks:
 *   1. Minimum 8 characters
 *   2. At least one uppercase letter
 *   3. At least one lowercase letter
 *   4. At least one digit
 *   5. At least one special character (non-alphanumeric, non-whitespace)
 *
 * Uppercase and lowercase are scored together as a single point (both must
 * be present to earn the point). This yields a score from 0 to 4.
 *
 * The failures array reports which individual checks failed.
 */
export function validatePasswordStrength(password: string): PasswordStrengthResult {
  const failures: PasswordCriterion[] = [];
  let score = 0;

  // Criterion 1: minimum length (>= 8 characters)
  if (password.length >= 8) {
    score++;
  } else {
    failures.push('minLength');
  }

  // Criterion 2: letter case — both uppercase and lowercase must be present
  const hasUppercase = /[A-Z]/.test(password);
  const hasLowercase = /[a-z]/.test(password);

  if (hasUppercase && hasLowercase) {
    score++;
  } else if (!hasUppercase) {
    failures.push('uppercase');
  } else {
    failures.push('lowercase');
  }

  // Criterion 3: at least one digit
  if (/[0-9]/.test(password)) {
    score++;
  } else {
    failures.push('digit');
  }

  // Criterion 4: at least one special character
  if (/[^A-Za-z0-9\s]/.test(password)) {
    score++;
  } else {
    failures.push('specialChar');
  }

  return { score, failures };
}
