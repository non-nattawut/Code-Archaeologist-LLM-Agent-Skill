export class ApiError extends Error {}

export function toMessage(err: unknown): string {
  return String(err);
}
