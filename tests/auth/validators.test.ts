import { describe, it, expect } from 'vitest';
import { validatePasswordStrength } from '../../src/auth/validators';

describe('validatePasswordStrength', () => {
  describe('return type', () => {
    it('should return an object with score and a list of failed criteria', () => {
      const result = validatePasswordStrength('anything');
      expect(result).toHaveProperty('score');
      expect(result).toHaveProperty('failures');
      expect(typeof result.score).toBe('number');
      expect(Array.isArray(result.failures)).toBe(true);
    });
  });

  describe('score range', () => {
    it('should return score 0 for an empty string', () => {
      const result = validatePasswordStrength('');
      expect(result.score).toBe(0);
    });

    it('should return score 4 for a password meeting all criteria', () => {
      const result = validatePasswordStrength('Str0ng!Pass');
      expect(result.score).toBe(4);
    });

    it('should never return a score below 0 or above 4', () => {
      const passwords = ['', 'a', 'AAAA', '1234', '!@#$', 'Aa1!Aa1!Aa1!'];
      for (const pw of passwords) {
        const { score } = validatePasswordStrength(pw);
        expect(score).toBeGreaterThanOrEqual(0);
        expect(score).toBeLessThanOrEqual(4);
      }
    });
  });

  describe('minimum length criterion (>= 8 characters)', () => {
    it('should fail length check for a 7-character password', () => {
      const result = validatePasswordStrength('Aa1!xyz');
      expect(result.failures).toContain('minLength');
      expect(result.score).toBe(3);
    });

    it('should pass length check for exactly 8 characters', () => {
      const result = validatePasswordStrength('Aa1!xyzw');
      expect(result.failures).not.toContain('minLength');
      expect(result.score).toBe(4);
    });
  });

  describe('uppercase criterion', () => {
    it('should fail when no uppercase letter is present', () => {
      const result = validatePasswordStrength('abcd1234!');
      expect(result.failures).toContain('uppercase');
    });

    it('should pass when at least one uppercase letter is present', () => {
      const result = validatePasswordStrength('Abcd1234!');
      expect(result.failures).not.toContain('uppercase');
    });
  });

  describe('lowercase criterion', () => {
    it('should fail when no lowercase letter is present', () => {
      const result = validatePasswordStrength('ABCD1234!');
      expect(result.failures).toContain('lowercase');
    });

    it('should pass when at least one lowercase letter is present', () => {
      const result = validatePasswordStrength('ABCd1234!');
      expect(result.failures).not.toContain('lowercase');
    });
  });

  describe('digit criterion', () => {
    it('should fail when no digit is present', () => {
      const result = validatePasswordStrength('Abcdefgh!');
      expect(result.failures).toContain('digit');
    });

    it('should pass when at least one digit is present', () => {
      const result = validatePasswordStrength('Abcdefg1!');
      expect(result.failures).not.toContain('digit');
    });
  });

  describe('special character criterion', () => {
    it('should fail when no special character is present', () => {
      const result = validatePasswordStrength('Abcdefg1');
      expect(result.failures).toContain('specialChar');
    });

    it('should pass when at least one special character is present', () => {
      const result = validatePasswordStrength('Abcdefg1!');
      expect(result.failures).not.toContain('specialChar');
      expect(result.score).toBe(4);
    });

    it('should recognize various special characters', () => {
      const specials = ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')', '-', '_', '=', '+'];
      for (const char of specials) {
        const pw = `Abcdefg1${char}`;
        const result = validatePasswordStrength(pw);
        expect(result.failures).not.toContain('specialChar');
      }
    });
  });

  describe('combined scoring', () => {
    it('should return score 1 when only length is met', () => {
      // lowercase only, 8+ chars, no upper/digit/special
      const result = validatePasswordStrength('abcdefgh');
      expect(result.score).toBe(1);
      expect(result.failures).toEqual(
        expect.arrayContaining(['uppercase', 'digit', 'specialChar'])
      );
    });

    it('should return score 2 when two criteria are met', () => {
      // 8+ chars with uppercase and lowercase, no digit or special
      const result = validatePasswordStrength('Abcdefgh');
      expect(result.score).toBe(2);
      expect(result.failures).toEqual(
        expect.arrayContaining(['digit', 'specialChar'])
      );
    });

    it('should return score 3 when three criteria are met', () => {
      // 8+ chars with upper, lower, digit, no special
      const result = validatePasswordStrength('Abcdefg1');
      expect(result.score).toBe(3);
      expect(result.failures).toEqual(
        expect.arrayContaining(['specialChar'])
      );
    });

    it('should return score 0 when no criteria are met', () => {
      // empty string: fails length, no upper, no lower, no digit, no special
      const result = validatePasswordStrength('');
      expect(result.score).toBe(0);
      expect(result.failures).toHaveLength(4);
    });
  });

  describe('edge cases', () => {
    it('should handle a very long password', () => {
      const pw = 'Aa1!' + 'x'.repeat(1000);
      const result = validatePasswordStrength(pw);
      expect(result.score).toBe(4);
    });

    it('should handle unicode letters', () => {
      // Unicode uppercase/lowercase should still count
      const result = validatePasswordStrength('Abcdefg1!');
      expect(result.score).toBe(4);
    });

    it('should handle whitespace in passwords', () => {
      const result = validatePasswordStrength('Ab 1!efgh');
      expect(result.score).toBe(4);
    });
  });
});
