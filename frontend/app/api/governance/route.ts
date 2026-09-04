import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../lib/server/api-client";
import { requireAccessToken } from "../../../lib/server/session";

export async function GET(): Promise<NextResponse> {
  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    const [apiKeys, retention] = await Promise.all([aegisApi.managedApiKeys(token), aegisApi.retentionPolicy(token)]);
    return NextResponse.json({ apiKeys, retention }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json({ detail: error instanceof AegisApiError ? error.message : "Governance controls are temporarily unavailable" }, { status: error instanceof AegisApiError ? error.status : 503 });
  }
}
