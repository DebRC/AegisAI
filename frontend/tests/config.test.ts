import assert from "node:assert/strict";
import test from "node:test";

import {
  FrontendConfigurationError,
  parseApiBaseUrl,
  parseRefreshCookieMaxAge,
  parseSecureCookieSetting,
} from "../lib/config.ts";

test("normalizes an absolute API base URL without a trailing slash", () => {
  assert.equal(parseApiBaseUrl("http://backend:8000/"), "http://backend:8000");
});

test("rejects missing and non-HTTP API base URLs", () => {
  assert.throws(() => parseApiBaseUrl(undefined), FrontendConfigurationError);
  assert.throws(() => parseApiBaseUrl("postgres://database"), FrontendConfigurationError);
});

test("uses secure cookies outside local development unless explicitly configured", () => {
  assert.equal(parseSecureCookieSetting(undefined, "production"), true);
  assert.equal(parseSecureCookieSetting(undefined, "development"), false);
  assert.equal(parseSecureCookieSetting("false", "production"), false);
  assert.throws(() => parseSecureCookieSetting("sometimes", "production"), FrontendConfigurationError);
});

test("bounds the refresh cookie lifetime", () => {
  assert.equal(parseRefreshCookieMaxAge(undefined), 604800);
  assert.equal(parseRefreshCookieMaxAge("3600"), 3600);
  assert.throws(() => parseRefreshCookieMaxAge("12.5"), FrontendConfigurationError);
});
