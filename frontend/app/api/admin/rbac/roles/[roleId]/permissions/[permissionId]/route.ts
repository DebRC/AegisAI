import { NextResponse } from "next/server";

import { AegisApiError, aegisApi } from "../../../../../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../../../../../lib/server/session";

type RouteContext = { params: Promise<{ roleId: string; permissionId: string }> };

function validId(value: string): boolean {
  return /^\d+$/.test(value) && Number(value) > 0;
}

async function routeIds(context: RouteContext): Promise<{ roleId: number; permissionId: number } | null> {
  const { roleId, permissionId } = await context.params;
  if (!validId(roleId) || !validId(permissionId)) return null;
  return { roleId: Number(roleId), permissionId: Number(permissionId) };
}

export async function POST(_: Request, context: RouteContext): Promise<NextResponse> {
  const ids = await routeIds(context);
  if (!ids) return NextResponse.json({ detail: "Invalid role permission request" }, { status: 422 });

  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    return NextResponse.json(await aegisApi.grantRolePermission(token, ids.roleId, ids.permissionId), { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof AegisApiError ? error.message : "Permission grant unavailable" },
      { status: error instanceof AegisApiError ? error.status : 503 },
    );
  }
}

export async function DELETE(_: Request, context: RouteContext): Promise<NextResponse> {
  const ids = await routeIds(context);
  if (!ids) return NextResponse.json({ detail: "Invalid role permission request" }, { status: 422 });

  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    await aegisApi.revokeRolePermission(token, ids.roleId, ids.permissionId);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    return NextResponse.json(
      { detail: error instanceof AegisApiError ? error.message : "Permission revocation unavailable" },
      { status: error instanceof AegisApiError ? error.status : 503 },
    );
  }
}
