import { config } from '../app/config';
import type {
  FailurePackage,
  Investigation,
  SystemHealthSnapshot,
} from '../types';
import { ApiError } from './apiTypes';
import type {
  ActionDecision,
  CreateInvestigationResponse,
  TriageZeroApi,
} from './apiTypes';

// Wire shape returned by the ingestion API for a created investigation.
// The backend speaks `investigation_id`; the frontend uses `id` internally.
interface CreateInvestigationWireResponse {
  investigation_id: string;
  status: 'received';
}

interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

// Surfaces the backend's own error message (and field-level details) so
// validation failures are actionable instead of a bare status code.
async function errorMessage(res: Response): Promise<string> {
  const fallback = `API request failed: ${res.status} ${res.statusText}`;
  try {
    const body = (await res.json()) as ApiErrorBody;
    const error = body.error;
    if (!error?.message) return fallback;

    const details = error.details;
    if (Array.isArray(details)) {
      const fields = details
        .map((d) =>
          typeof d === 'object' && d !== null && 'field' in d
            ? String((d as { field: unknown }).field)
            : null,
        )
        .filter(Boolean)
        .slice(0, 5);
      if (fields.length > 0) return `${error.message} (${fields.join(', ')})`;
    }
    if (
      details &&
      typeof details === 'object' &&
      'forbidden_fields' in details &&
      Array.isArray((details as { forbidden_fields: unknown[] }).forbidden_fields)
    ) {
      const forbidden = (details as { forbidden_fields: string[] }).forbidden_fields;
      return `${error.message} (${forbidden.slice(0, 5).join(', ')})`;
    }
    return error.message;
  } catch {
    return fallback;
  }
}

/**
 * Supplies the current Firebase ID token, or null when signed out /
 * unconfigured. Installed by AuthProvider so this module never imports
 * Firebase directly and stays trivially testable.
 */
type AuthTokenProvider = () => Promise<string | null>;

let authTokenProvider: AuthTokenProvider | null = null;

export function setAuthTokenProvider(provider: AuthTokenProvider | null): void {
  authTokenProvider = provider;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (!authTokenProvider) return {};
  try {
    const token = await authTokenProvider();
    return token ? { authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    const auth = await authHeaders();
    res = await fetch(`${config.apiBaseUrl}${path}`, {
      ...init,
      headers: { 'content-type': 'application/json', ...auth, ...init?.headers },
    });
  } catch {
    throw new ApiError(`Could not reach TriageZero API at ${config.apiBaseUrl}`);
  }
  if (!res.ok) {
    throw new ApiError(await errorMessage(res), res.status);
  }
  return (await res.json()) as T;
}

export const httpApi: TriageZeroApi = {
  getHealth: () => request<SystemHealthSnapshot>('/api/v1/health'),

  listInvestigations: () => request<Investigation[]>('/api/v1/investigations'),

  getInvestigation: (id: string) =>
    request<Investigation>(`/api/v1/investigations/${encodeURIComponent(id)}`),

  createInvestigation: async (pkg: FailurePackage): Promise<CreateInvestigationResponse> => {
    const res = await request<CreateInvestigationWireResponse>('/api/v1/investigations', {
      method: 'POST',
      body: JSON.stringify(pkg),
    });
    return { id: res.investigation_id, status: res.status };
  },

  retryInvestigation: (id: string) =>
    request<Investigation>(
      `/api/v1/investigations/${encodeURIComponent(id)}/retry`,
      { method: 'POST' },
    ),

  // records the decision server-side; the backend never executes external actions
  decideAction: (id: string, decision: ActionDecision) =>
    request<Investigation>(
      `/api/v1/investigations/${encodeURIComponent(id)}/actions/${decision}`,
      { method: 'POST' },
    ),
};
