import { NextResponse } from "next/server";
import { apiBaseUrl } from "../../../../lib/server/config";
import { requireAccessToken } from "../../../../lib/server/session";

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();
  const token = await requireAccessToken();
  if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  try {
    const response = await fetch(`${apiBaseUrl()}/chat/stream`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", Accept: "text/event-stream" }, body, cache: "no-store" });
    if (!response.ok || !response.body) return NextResponse.json({ detail: "Grounded chat is temporarily unavailable" }, { status: response.status >= 400 && response.status < 500 ? response.status : 503 });
    return new Response(response.body, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no" } });
  } catch { return NextResponse.json({ detail: "Grounded chat is temporarily unavailable" }, { status: 503 }); }
}
