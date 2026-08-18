# Enterprise SSO account linking

AegisAI supports Google OpenID Connect, GitHub OAuth, and Microsoft Entra ID.
The browser flow uses short-lived signed state and PKCE; OpenID Connect flows
also validate a nonce. Provider tokens prove external identity but never become
AegisAI authorization credentials.

An existing provider-and-subject link always resolves to the linked local user.
A new identity can link to an existing local account only when the provider
supplies an exactly matching, verified email. A verified email without a local
match creates a just-in-time local account. Missing or unverified email is
rejected.

New SSO users receive no AegisAI role automatically. An administrator must
grant a local role before protected management actions are permitted.
