import { NextResponse } from "next/server";
import { AegisApiError, aegisApi } from "../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../lib/server/session";
export async function GET(): Promise<NextResponse> { try { const token = await requireAccessToken(); if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 }); return NextResponse.json(await aegisApi.adminUsers(token)); } catch (e) { return NextResponse.json({ detail: e instanceof AegisApiError ? e.message : "User administration unavailable" }, { status: e instanceof AegisApiError ? e.status : 503 }); } }
