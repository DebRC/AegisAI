import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../lib/server/api-client";
import { requireAccessToken } from "../../../lib/server/session";

function error(error: unknown): NextResponse {
  if (error instanceof AegisApiError && [403, 422].includes(error.status)) return NextResponse.json({ detail: error.message }, { status: error.status });
  return NextResponse.json({ detail: "Documents are temporarily unavailable" }, { status: 503 });
}

export async function GET(): Promise<NextResponse> {
  try {
    const accessToken = await requireAccessToken();
    if (!accessToken) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    return NextResponse.json(await aegisApi.documents(accessToken), { headers: { "Cache-Control": "no-store" } });
  } catch (cause) { return error(cause); }
}

export async function POST(request: Request): Promise<NextResponse> {
  try {
    const accessToken = await requireAccessToken();
    if (!accessToken) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    const body = await request.formData();
    if (!(body.get("file") instanceof File)) return NextResponse.json({ detail: "Choose a document to upload" }, { status: 422 });
    return NextResponse.json(await aegisApi.uploadDocument(accessToken, body), { status: 201, headers: { "Cache-Control": "no-store" } });
  } catch (cause) { return error(cause); }
}
