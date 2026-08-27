export class FrontendConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FrontendConfigurationError";
  }
}

export function parseApiBaseUrl(value: string | undefined): string {
  if (!value) {
    throw new FrontendConfigurationError("API_BASE_URL must be configured on the server");
  }

  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new FrontendConfigurationError("API_BASE_URL must be an absolute HTTP(S) URL");
  }

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new FrontendConfigurationError("API_BASE_URL must use HTTP or HTTPS");
  }

  url.pathname = "";
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/$/, "");
}

export function parseSecureCookieSetting(
  value: string | undefined,
  nodeEnvironment: string | undefined,
): boolean {
  if (value === undefined || value === "") {
    return nodeEnvironment === "production";
  }

  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }

  throw new FrontendConfigurationError("SESSION_COOKIE_SECURE must be true or false");
}

export function parseRefreshCookieMaxAge(value: string | undefined): number {
  if (value === undefined || value === "") {
    return 7 * 24 * 60 * 60;
  }

  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 60 || parsed > 90 * 24 * 60 * 60) {
    throw new FrontendConfigurationError(
      "SESSION_REFRESH_COOKIE_MAX_AGE_SECONDS must be an integer between 60 and 7776000",
    );
  }
  return parsed;
}
