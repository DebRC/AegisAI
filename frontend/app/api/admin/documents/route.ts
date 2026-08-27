import { NextResponse } from "next/server";
import { aegisApi } from "../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../lib/server/session";
export async function GET(): Promise<NextResponse> { const token = await requireAccessToken(); if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 }); try { return NextResponse.json(await aegisApi.adminDocuments(token)); } catch { return NextResponse.json({ detail: "Document administration unavailable" }, { status: 503 }); } }
