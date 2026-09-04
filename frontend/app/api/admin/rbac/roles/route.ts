import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../../lib/server/session";

type CreateRoleBody = { name?: unknown; description?: unknown };

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json().catch(() => ({})) as CreateRoleBody;
  const name = typeof body.name === "string" ? body.name.trim() : "";
  const description = typeof body.description === "string" ? body.description.trim() : "";

  if (name.length < 2 || name.length > 100 || description.length > 255) {
    return NextResponse.json({ detail: "Enter a role name between 2 and 100 characters" }, { status: 422 });
  }

  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });

    return NextResponse.json(
      await aegisApi.createRole(token, name, description || null),
      { status: 201 },
    );
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof AegisApiError ? error.message : "Role creation unavailable" },
      { status: error instanceof AegisApiError ? error.status : 503 },
    );
  }
}
