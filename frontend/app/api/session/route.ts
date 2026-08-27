import { NextResponse } from "next/server";

import { AegisApiError } from "../../../lib/server/api-client";
import { resolveSessionStatus } from "../../../lib/server/session";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  try {
    return NextResponse.json(await resolveSessionStatus(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    if (error instanceof AegisApiError) {
      return NextResponse.json(
        { detail: "AegisAI authentication is temporarily unavailable" },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    return NextResponse.json(
      { detail: "AegisAI authentication is temporarily unavailable" },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}
