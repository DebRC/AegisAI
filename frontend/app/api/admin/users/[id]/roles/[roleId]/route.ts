import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../../../../lib/server/session";

type RouteContext = { params: Promise<{ id: string; roleId: string }> };

function validId(value: string): boolean {
  return /^\d+$/.test(value) && Number(value) > 0;
}

export async function POST(_: Request, context: RouteContext): Promise<NextResponse> {
  const { id, roleId } = await context.params;
  if (!validId(id) || !validId(roleId)) {
    return NextResponse.json({ detail: "Invalid role assignment request" }, { status: 422 });
  }

  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });

    return NextResponse.json(
      await aegisApi.assignUserRole(token, Number(id), Number(roleId)),
      { status: 201 },
    );
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof AegisApiError ? error.message : "Role assignment unavailable" },
      { status: error instanceof AegisApiError ? error.status : 503 },
    );
  }
}
