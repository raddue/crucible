/**
 * Formats a number as a US currency string.
 * Example: 1234.5 -> "$1,234.50"
 */
export function formatCurrency(amount: number): string {
  const fixed = amount.toFixed(2);
  const [whole, decimal] = fixed.split(".");
  const withCommas = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `$${withCommas}.${decimal}`;
}
