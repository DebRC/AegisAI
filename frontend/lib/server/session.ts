import "server-only";

import { cookies } from "next/headers";

import type { AegisTokenPair, AegisUser, SessionStatus } from "../api/types";
import { AegisApiError, aegisApi } from "./api-client";
import { refreshCookieMaxAge, useSecureSessionCookies } from "./config";

const ACCESS_COOKIE = "aegis_access_token";
const REFRESH_COOKIE = "aegis_refresh_token";

type TokenCookies = {
  accessToken: string;
  refreshToken: string;
};

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    maxAge,
    path: "/",
    sameSite: "lax" as const,
    secure: useSecureSessionCookies(),
  };
}

export async function readTokenCookies(): Promise<TokenCookies | null> {
  const store = await cookies();
  const accessToken = store.get(ACCESS_COOKIE)?.value;
  const refreshToken = store.get(REFRESH_COOKIE)?.value;
  if (!accessToken || !refreshToken) {
    return null;
  }
  return { accessToken, refreshToken };
}

export async function writeTokenCookies(tokens: AegisTokenPair): Promise<void> {
  const store = await cookies();
  store.set(ACCESS_COOKIE, tokens.access_token, cookieOptions(tokens.expires_in));
  store.set(REFRESH_COOKIE, tokens.refresh_token, cookieOptions(refreshCookieMaxAge()));
}

export async function clearTokenCookies(): Promise<void> {
  const store = await cookies();
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}

export async function resolveSessionStatus(): Promise<SessionStatus> {
  const tokens = await readTokenCookies();
  if (!tokens) {
    return { authenticated: false };
  }

  let user: AegisUser;
  try {
    user = await aegisApi.currentUser(tokens.accessToken);
  } catch (error) {
    if (!(error instanceof AegisApiError) || error.status !== 401) {
      throw error;
    }

    try {
      const refreshedTokens = await aegisApi.refresh(tokens.refreshToken);
      await writeTokenCookies(refreshedTokens);
      user = await aegisApi.currentUser(refreshedTokens.access_token);
    } catch (refreshError) {
      if (refreshError instanceof AegisApiError && refreshError.status === 401) {
        await clearTokenCookies();
        return { authenticated: false };
      }
      throw refreshError;
    }
  }

  return { authenticated: true, user };
}

export async function requireAccessToken(): Promise<string | null> {
  const tokens = await readTokenCookies();
  if (!tokens) return null;
  try {
    await aegisApi.currentUser(tokens.accessToken);
    return tokens.accessToken;
  } catch (error) {
    if (!(error instanceof AegisApiError) || error.status !== 401) throw error;
    try {
      const refreshed = await aegisApi.refresh(tokens.refreshToken);
      await writeTokenCookies(refreshed);
      return refreshed.access_token;
    } catch (refreshError) {
      if (refreshError instanceof AegisApiError && refreshError.status === 401) await clearTokenCookies();
      return null;
    }
  }
}
