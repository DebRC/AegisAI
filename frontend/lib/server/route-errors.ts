import { NextResponse } from "next/server";

import { AegisApiError } from "./api-client";

export function authenticationErrorResponse(error: unknown): NextResponse {
  if (error instanceof AegisApiError && [400, 401, 409, 422].includes(error.status)) {
    return NextResponse.json({ detail: error.message }, { status: error.status });
  }
  return NextResponse.json(
    { detail: "AegisAI authentication is temporarily unavailable" },
    { status: 503 },
  );
}
