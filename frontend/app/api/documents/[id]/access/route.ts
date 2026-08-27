import { NextResponse } from "next/server";
import { AegisApiError, aegisApi } from "../../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../../lib/server/session";
export async function GET(_: Request, context: { params: Promise<{ id: string }> }): Promise<NextResponse> { const { id } = await context.params; try { const token = await requireAccessToken(); if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 }); return NextResponse.json(await aegisApi.documentAccess(token, Number(id))); } catch (e) { return NextResponse.json({ detail: e instanceof AegisApiError ? e.message : "Access details unavailable" }, { status: e instanceof AegisApiError ? e.status : 503 }); } }
