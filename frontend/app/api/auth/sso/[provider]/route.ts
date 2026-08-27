import { NextResponse } from "next/server";

import { apiBaseUrl } from "../../../../../lib/server/config";

const PROVIDERS = new Set(["google", "github", "microsoft_entra"]);

export async function GET(
  _: Request,
  context: { params: Promise<{ provider: string }> },
): Promise<NextResponse> {
  const { provider } = await context.params;
  if (!PROVIDERS.has(provider)) {
    return NextResponse.json({ detail: "Unsupported SSO provider" }, { status: 404 });
  }
  return NextResponse.redirect(`${apiBaseUrl()}/auth/sso/${provider}`, 307);
}
