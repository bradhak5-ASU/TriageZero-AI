import { config } from '../app/config';
import type {
  FailurePackage,
  Investigation,
  SystemHealthSnapshot,
} from '../types';
import { ApiError } from './apiTypes';
import type { CreateInvestigationResponse, TriageZeroApi } from './apiTypes';

// Wire shape returned by the ingestion API for a created investigation.
// The backend speaks `investigation_id`; the frontend uses `id` internally.
interface CreateInvestigationWireResponse {
  investigation_id: string;
  status: 'received';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${config.apiBaseUrl}${path}`, {
      headers: { 'content-type': 'application/json', ...init?.headers },
      ...init,
    });
  } catch {
    throw new ApiError(`Could not reach TriageZero API at ${config.apiBaseUrl}`);
  }
  if (!res.ok) {
    throw new ApiError(`API request failed: ${res.status} ${res.statusText}`, res.status);
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
};
