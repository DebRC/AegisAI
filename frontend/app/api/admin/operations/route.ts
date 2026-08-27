import { NextResponse } from "next/server";
import { aegisApi } from "../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../lib/server/session";
export async function GET(): Promise<NextResponse> { const token = await requireAccessToken(); if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 }); try { const [jobs, audit] = await Promise.all([aegisApi.adminJobs(token), aegisApi.auditEvents(token)]); return NextResponse.json({ jobs, audit: audit.items }); } catch { return NextResponse.json({ detail: "Operations unavailable" }, { status: 503 }); } }
