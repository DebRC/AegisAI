import { NextResponse } from "next/server";

import { aegisApi } from "../../../../lib/server/api-client";
import { clearTokenCookies, readTokenCookies } from "../../../../lib/server/session";

export async function POST(): Promise<NextResponse> {
  const tokens = await readTokenCookies();
  try {
    if (tokens) {
      await aegisApi.logout(tokens.refreshToken);
    }
  } finally {
    await clearTokenCookies();
  }
  return new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
}
