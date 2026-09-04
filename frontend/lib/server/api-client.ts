import "server-only";

import type { AdminOverview, AdminUserPage, AegisDocument, AegisLoginResponse, AegisTokenPair, AegisUser, DocumentDetailData, DocumentPage, RetrievalResponse, TenantMembership, ManagedApiKey, RetentionPolicy } from "../api/types";
import { apiBaseUrl } from "./config";

export class AegisApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "AegisApiError";
  }
}

type ErrorPayload = { detail?: unknown };

function safeErrorDetail(payload: unknown): string {
  const detail = payload && typeof payload === "object" ? (payload as ErrorPayload).detail : undefined;
  if (typeof detail === "string") {
    return detail.slice(0, 255);
  }
  return "The AegisAI service could not complete this request";
}

async function backendRequest<T>(
  path: string,
  init: RequestInit,
): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...init.headers,
    },
    signal: AbortSignal.timeout(10_000),
  });

  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    throw new AegisApiError(response.status, safeErrorDetail(payload));
  }
  return payload as T;
}

export const aegisApi = {
  register(email: string, fullName: string, password: string): Promise<AegisUser> {
    return backendRequest<AegisUser>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, full_name: fullName, password }),
    });
  },

  login(email: string, password: string): Promise<AegisLoginResponse> {
    return backendRequest<AegisLoginResponse>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
  },

  currentUser(accessToken: string): Promise<AegisUser> {
    return backendRequest<AegisUser>("/auth/me", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  },

  refresh(refreshToken: string): Promise<AegisTokenPair> {
    return backendRequest<AegisTokenPair>("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  },

  logout(refreshToken: string): Promise<void> {
    return backendRequest<void>("/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  },

  documents(accessToken: string): Promise<DocumentPage> {
    return backendRequest<DocumentPage>("/documents", { headers: { Authorization: `Bearer ${accessToken}` } });
  },

  uploadDocument(accessToken: string, body: FormData): Promise<AegisDocument> {
    return backendRequest<AegisDocument>("/documents", { method: "POST", headers: { Authorization: `Bearer ${accessToken}` }, body });
  },

  documentDetail(accessToken: string, documentId: number): Promise<DocumentDetailData> {
    return Promise.all([
      backendRequest<AegisDocument>(`/documents/${documentId}`, { headers: { Authorization: `Bearer ${accessToken}` } }),
      backendRequest<DocumentDetailData["extraction"]>(`/documents/${documentId}/extraction`, { headers: { Authorization: `Bearer ${accessToken}` } }).catch(() => null),
      backendRequest<DocumentDetailData["indexing"]>(`/documents/${documentId}/indexing-status`, { headers: { Authorization: `Bearer ${accessToken}` } }).catch(() => null),
      backendRequest<{ items: DocumentDetailData["jobs"] }>(`/documents/${documentId}/processing-jobs`, { headers: { Authorization: `Bearer ${accessToken}` } }),
    ]).then(([document, extraction, indexing, jobs]) => ({ document, extraction, indexing, jobs: jobs.items }));
  },

  renameDocument(accessToken: string, documentId: number, title: string): Promise<AegisDocument> {
    return backendRequest<AegisDocument>(`/documents/${documentId}`, { method: "PATCH", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ title }) });
  },
  deleteDocument(accessToken: string, documentId: number): Promise<void> {
    return backendRequest<void>(`/documents/${documentId}`, { method: "DELETE", headers: { Authorization: `Bearer ${accessToken}` } });
  },
  reprocessDocument(accessToken: string, documentId: number): Promise<unknown> {
    return backendRequest(`/documents/${documentId}/reprocess`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } });
  },
  documentAccess(accessToken: string, documentId: number): Promise<unknown> { return backendRequest(`/documents/${documentId}/access`, { headers: { Authorization: `Bearer ${accessToken}` } }); },
  grantDocumentAccess(accessToken: string, documentId: number, userId: number, accessLevel: "read" | "write"): Promise<unknown> { return backendRequest(`/documents/${documentId}/access/${userId}`, { method: "PUT", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ access_level: accessLevel }) }); },
  revokeDocumentAccess(accessToken: string, documentId: number, userId: number): Promise<void> { return backendRequest(`/documents/${documentId}/access/${userId}`, { method: "DELETE", headers: { Authorization: `Bearer ${accessToken}` } }); },
  search(accessToken: string, query: string): Promise<RetrievalResponse> { return backendRequest("/retrieval/search", { method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ query, limit: 10 }) }); },
  adminOverview(accessToken: string): Promise<AdminOverview> { return backendRequest("/admin/overview", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  adminUsers(accessToken: string): Promise<AdminUserPage> { return backendRequest("/admin/users", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  setAdminUserStatus(accessToken: string, userId: number, isActive: boolean): Promise<unknown> { return backendRequest(`/admin/users/${userId}/status`, { method: "PATCH", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ is_active: isActive }) }); },
  assignUserRole(accessToken: string, userId: number, roleId: number): Promise<unknown> { return backendRequest(`/rbac/users/${userId}/roles/${roleId}`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } }); },
  adminRoles(accessToken: string): Promise<import("../api/types").AdminRole[]> { return backendRequest("/admin/roles", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  adminPermissions(accessToken: string): Promise<import("../api/types").AdminPermission[]> { return backendRequest("/admin/permissions", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  adminDocuments(accessToken: string): Promise<import("../api/types").AdminDocumentPage> { return backendRequest("/admin/documents", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  adminJobs(accessToken: string): Promise<import("../api/types").AdminJob[]> { return backendRequest("/admin/processing-jobs", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  auditEvents(accessToken: string): Promise<{ items: import("../api/types").AuditEvent[] }> { return backendRequest("/audit-events", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  tenants(accessToken: string): Promise<TenantMembership[]> { return backendRequest("/tenants", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  selectTenant(accessToken: string, tenantId: number): Promise<AegisLoginResponse> { return backendRequest(`/tenants/${tenantId}/select`, { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } }); },
  managedApiKeys(accessToken: string): Promise<ManagedApiKey[]> { return backendRequest("/governance/api-keys", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  createManagedApiKey(accessToken: string, name: string, scopes: string[], expiresAt?: string): Promise<ManagedApiKey & { api_key: string }> { return backendRequest("/governance/api-keys", { method: "POST", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ name, scopes, ...(expiresAt ? { expires_at: expiresAt } : {}) }) }); },
  revokeManagedApiKey(accessToken: string, id: number): Promise<void> { return backendRequest(`/governance/api-keys/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${accessToken}` } }); },
  retentionPolicy(accessToken: string): Promise<RetentionPolicy> { return backendRequest("/governance/retention", { headers: { Authorization: `Bearer ${accessToken}` } }); },
  updateRetentionPolicy(accessToken: string, days: number | null): Promise<RetentionPolicy> { return backendRequest("/governance/retention", { method: "PUT", headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" }, body: JSON.stringify({ document_retention_days: days }) }); },
};
