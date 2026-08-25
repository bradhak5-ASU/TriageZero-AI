import { config } from '../app/config';
import { httpApi } from './httpApi';
import { mockApi } from './mockApi';
import type { TriageZeroApi } from './apiTypes';

export const api: TriageZeroApi = config.useMockApi ? mockApi : httpApi;

export { ApiError } from './apiTypes';
export type { TriageZeroApi, CreateInvestigationResponse } from './apiTypes';
