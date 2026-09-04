import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../lib/server/session";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json().catch(() => ({})) as { name?: unknown; scopes?: unknown };
  if (typeof body.name !== "string" || !Array.isArray(body.scopes) || body.scopes.some(scope => typeof scope !== "string")) {
    return NextResponse.json({ detail: "Provide a key name and one or more scopes" }, { status: 422 });
  }
  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    return NextResponse.json(await aegisApi.createManagedApiKey(token, body.name, body.scopes), { status: 201, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ detail: error instanceof AegisApiError ? error.message : "API key creation unavailable" }, { status: error instanceof AegisApiError ? error.status : 503 });
  }
}
