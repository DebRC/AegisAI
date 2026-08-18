# Refresh token lifecycle

Password login and verified SSO issue a short-lived access token plus a longer
lived refresh token. Clients send the access token as `Authorization: Bearer`
on protected requests. They send a refresh token only to the refresh or logout
endpoint.

Refreshing a session rotates the token pair. The previously used refresh token
is revoked and cannot create another session. Logout soft-revokes the supplied
refresh token; a previously issued access token remains usable only until its
short expiry.

Never put tokens in documents, logs, screenshots, or support tickets. Rotate a
token that has been exposed.
