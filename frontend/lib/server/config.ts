import "server-only";

import {
  parseApiBaseUrl,
  parseRefreshCookieMaxAge,
  parseSecureCookieSetting,
} from "../config";

export function apiBaseUrl(): string {
  return parseApiBaseUrl(process.env.API_BASE_URL);
}

export function useSecureSessionCookies(): boolean {
  return parseSecureCookieSetting(process.env.SESSION_COOKIE_SECURE, process.env.NODE_ENV);
}

export function refreshCookieMaxAge(): number {
  return parseRefreshCookieMaxAge(process.env.SESSION_REFRESH_COOKIE_MAX_AGE_SECONDS);
}
