import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../lib/server/session";

export async function PUT(request: Request): Promise<NextResponse> {
  const body = await request.json().catch(() => ({})) as { document_retention_days?: unknown };
  const days = body.document_retention_days;
  if (days !== null && (!Number.isInteger(days) || (days as number) < 1)) return NextResponse.json({ detail: "Retention days must be a positive whole number or null" }, { status: 422 });
  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    return NextResponse.json(await aegisApi.updateRetentionPolicy(token, days as number | null), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ detail: error instanceof AegisApiError ? error.message : "Retention update unavailable" }, { status: error instanceof AegisApiError ? error.status : 503 });
  }
}
