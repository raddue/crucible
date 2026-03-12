import { describe, it, expect } from "vitest";
import { formatCurrency } from "../format";

describe("formatCurrency", () => {
  it("should format 1 as $1.00", () => {
    expect(formatCurrency(1)).toBe("$1.00");
  });

  it("should format 0 as $0.00", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("should format 1234.5 as $1,234.50", () => {
    expect(formatCurrency(1234.5)).toBe("$1,234.50");
  });

  it("should format 1000000 as $1,000,000.00", () => {
    expect(formatCurrency(1000000)).toBe("$1,000,000.00");
  });

  it("should format 99.99 as $99.99", () => {
    expect(formatCurrency(99.99)).toBe("$99.99");
  });

  it("should format 0.5 as $0.50", () => {
    expect(formatCurrency(0.5)).toBe("$0.50");
  });

  it("uses a period (not comma) as the decimal separator", () => {
    const result = formatCurrency(1);
    expect(result).toBe("$1.00");
    expect(result).not.toContain(",");
  });
});
