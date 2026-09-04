import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../../../lib/server/api-client";
import { requireAccessToken, writeTokenCookies } from "../../../../../lib/server/session";

export async function POST(_: Request, context: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const { id } = await context.params;
  if (!/^\d+$/.test(id)) return NextResponse.json({ detail: "Organization not found" }, { status: 404 });
  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    const session = await aegisApi.selectTenant(token, Number(id));
    await writeTokenCookies(session);
    return NextResponse.json({ tenant_id: session.tenant_id }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ detail: error instanceof AegisApiError ? error.message : "Organization switch unavailable" }, { status: error instanceof AegisApiError ? error.status : 503 });
  }
}
