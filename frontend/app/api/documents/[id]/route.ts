import { NextResponse } from "next/server";
import { AegisApiError, aegisApi } from "../../../../lib/server/api-client";
import { requireAccessToken } from "../../../../lib/server/session";

export async function GET(_: Request, context: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const { id } = await context.params;
  if (!/^\d+$/.test(id)) return NextResponse.json({ detail: "Document not found" }, { status: 404 });
  try {
    const token = await requireAccessToken();
    if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
    return NextResponse.json(await aegisApi.documentDetail(token, Number(id)), { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof AegisApiError && [403, 404].includes(error.status)) return NextResponse.json({ detail: "Document unavailable" }, { status: 404 });
    return NextResponse.json({ detail: "Document details are temporarily unavailable" }, { status: 503 });
  }
}

async function documentId(context: { params: Promise<{ id: string }> }): Promise<number | null> { const { id } = await context.params; return /^\d+$/.test(id) ? Number(id) : null; }
async function tokenResponse() { const token = await requireAccessToken(); return token; }
export async function PATCH(request: Request, context: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const id = await documentId(context); const title = (await request.json().catch(() => ({})) as { title?: unknown }).title;
  if (!id || typeof title !== "string" || !title.trim()) return NextResponse.json({ detail: "A document title is required" }, { status: 422 });
  try { const token = await tokenResponse(); if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 }); return NextResponse.json(await aegisApi.renameDocument(token, id, title.trim())); } catch (error) { return NextResponse.json({ detail: error instanceof AegisApiError ? error.message : "Document update failed" }, { status: error instanceof AegisApiError ? error.status : 503 }); }
}
export async function DELETE(_: Request, context: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const id = await documentId(context); if (!id) return NextResponse.json({ detail: "Document not found" }, { status: 404 });
  try { const token = await tokenResponse(); if (!token) return NextResponse.json({ detail: "Authentication required" }, { status: 401 }); await aegisApi.deleteDocument(token, id); return new NextResponse(null, { status: 204 }); } catch (error) { return NextResponse.json({ detail: error instanceof AegisApiError ? error.message : "Document deletion failed" }, { status: error instanceof AegisApiError ? error.status : 503 }); }
}
