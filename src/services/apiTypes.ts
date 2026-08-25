import type {
  FailurePackage,
  Investigation,
  SystemHealthSnapshot,
} from '../types';

export interface CreateInvestigationResponse {
  id: string;
  status: 'received';
}

// The contract both the real HTTP client and the mock client implement.
export interface TriageZeroApi {
  getHealth(): Promise<SystemHealthSnapshot>;
  listInvestigations(): Promise<Investigation[]>;
  getInvestigation(id: string): Promise<Investigation>;
  createInvestigation(pkg: FailurePackage): Promise<CreateInvestigationResponse>;
  retryInvestigation(id: string): Promise<Investigation>;
}

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
