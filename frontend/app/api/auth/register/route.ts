import { NextResponse } from "next/server";

import { aegisApi } from "../../../../lib/server/api-client";
import { authenticationErrorResponse } from "../../../../lib/server/route-errors";

export async function POST(request: Request): Promise<NextResponse> {
  const body: unknown = await request.json().catch(() => undefined);
  const value = body as { email?: unknown; fullName?: unknown; password?: unknown } | undefined;
  const email = typeof value?.email === "string" ? value.email.trim() : "";
  const fullName = typeof value?.fullName === "string" ? value.fullName.trim() : "";
  const password = typeof value?.password === "string" ? value.password : "";
  if (!email || !fullName || !password) {
    return NextResponse.json({ detail: "Email, full name, and password are required" }, { status: 422 });
  }

  try {
    const user = await aegisApi.register(email, fullName, password);
    return NextResponse.json({ user }, { status: 201, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return authenticationErrorResponse(error);
  }
}
