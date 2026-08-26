import { afterEach, describe, expect, it, vi } from 'vitest';
import { httpApi } from '../services/httpApi';
import { sampleFailurePackage } from '../data/samplePackage';

function stubFetch(payload: unknown, ok = true, status = 200) {
  const fn = vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Server Error',
    json: () => Promise.resolve(payload),
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('real HTTP adapter', () => {
  it('maps the ingestion wire response investigation_id to the internal id', async () => {
    const fetchMock = stubFetch({
      investigation_id: 'INV-A1B2C3D4',
      status: 'received',
      received_at: '2026-08-25T18:01:00Z',
    });

    const res = await httpApi.createInvestigation(sampleFailurePackage);

    expect(res).toEqual({ id: 'INV-A1B2C3D4', status: 'received' });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/investigations$/);
    expect(init.method).toBe('POST');
  });

  it('posts action decisions to the actions endpoint and returns the investigation', async () => {
    const updated = { id: 'INV-A1B2C3D4', recommendedAction: { approvalState: 'approved' } };
    const fetchMock = stubFetch(updated);

    const res = await httpApi.decideAction('INV-A1B2C3D4', 'approve');

    expect(res).toEqual(updated);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/investigations\/INV-A1B2C3D4\/actions\/approve$/);
    expect(init.method).toBe('POST');
  });

  it('accepts the backend health payload, including its extra status field', async () => {
    stubFetch({
      status: 'ok',
      overall: 'healthy',
      services: [
        {
          id: 'gemini',
          name: 'Gemini',
          status: 'disabled',
          lastCheck: '2026-08-25T18:01:00Z',
          region: '—',
          detail: 'Not connected in the local milestone',
        },
      ],
      queueDepth: 0,
      workerThroughputPerMin: 0,
      ingestionLastHour: 1,
      ingestionVolume: [{ label: 'now', count: 1 }],
      events: [],
    });

    const health = await httpApi.getHealth();

    expect(health.overall).toBe('healthy');
    expect(health.services[0].status).toBe('disabled');
    expect(health.ingestionLastHour).toBe(1);
  });

  it('raises a helpful ApiError on non-2xx responses', async () => {
    stubFetch({ error: { code: 'not_found' } }, false, 404);
    await expect(httpApi.getInvestigation('INV-NOPE')).rejects.toThrow(/404/);
  });

  it('surfaces the server error message and offending field paths', async () => {
    stubFetch(
      {
        error: {
          code: 'private_oracle_fields',
          message: 'Package contains private QA-oracle fields and was rejected.',
          details: {
            forbidden_fields: ['failure.private_oracle', 'failure.private_oracle.scenario_name'],
          },
        },
      },
      false,
      422,
    );

    await expect(httpApi.createInvestigation(sampleFailurePackage)).rejects.toThrow(
      /private QA-oracle fields.*failure\.private_oracle/s,
    );
  });

  it('surfaces field-level validation details from a strict-schema rejection', async () => {
    stubFetch(
      {
        error: {
          code: 'validation_error',
          message: 'Failure package failed validation.',
          details: [{ field: 'environment.browser', message: 'unexpected value' }],
        },
      },
      false,
      422,
    );

    await expect(httpApi.createInvestigation(sampleFailurePackage)).rejects.toThrow(
      /environment\.browser/,
    );
  });
});
