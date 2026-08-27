import { NextResponse } from "next/server";

import { aegisApi } from "../../../../lib/server/api-client";
import { authenticationErrorResponse } from "../../../../lib/server/route-errors";
import { writeTokenCookies } from "../../../../lib/server/session";

export async function POST(request: Request): Promise<NextResponse> {
  const body: unknown = await request.json().catch(() => undefined);
  const email = body && typeof body === "object" && typeof (body as { email?: unknown }).email === "string"
    ? (body as { email: string }).email.trim()
    : "";
  const password = body && typeof body === "object" && typeof (body as { password?: unknown }).password === "string"
    ? (body as { password: string }).password
    : "";
  if (!email || !password) {
    return NextResponse.json({ detail: "Email and password are required" }, { status: 422 });
  }

  try {
    const session = await aegisApi.login(email, password);
    await writeTokenCookies(session);
    return NextResponse.json({ user: session.user }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return authenticationErrorResponse(error);
  }
}
