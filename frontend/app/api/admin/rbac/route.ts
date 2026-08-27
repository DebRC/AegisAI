import { NextResponse } from "next/server";
import { aegisApi } from "../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../lib/server/session";
export async function GET(): Promise<NextResponse> { const token = await requireAccessToken(); if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 }); try { const [roles, permissions] = await Promise.all([aegisApi.adminRoles(token), aegisApi.adminPermissions(token)]); return NextResponse.json({ roles, permissions }); } catch { return NextResponse.json({ detail: "RBAC administration unavailable" }, { status: 503 }); } }
