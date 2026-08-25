import type { FailurePackage } from '../types';

// Fields that belong to the private QA oracle. They must never reach the
// AI investigation pipeline, so the UI rejects them loudly at the door.
// This is a demonstration safeguard — the backend enforces the real boundary.
export const FORBIDDEN_ORACLE_FIELDS = [
  'expected_classification',
  'expected_severity',
  'expected_release_risk',
  'expected_action',
  'private_oracle',
  'oracle',
  'controlled_defect',
  'defect_scenario',
  'scenario_name',
] as const;

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  forbiddenFields: string[];
  pkg?: FailurePackage;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function findForbiddenKeys(value: unknown, path = ''): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item, i) => findForbiddenKeys(item, `${path}[${i}]`));
  }
  if (!isObject(value)) return [];
  return Object.entries(value).flatMap(([key, child]) => {
    const keyPath = path ? `${path}.${key}` : key;
    const hits = (FORBIDDEN_ORACLE_FIELDS as readonly string[]).includes(key)
      ? [keyPath]
      : [];
    return [...hits, ...findForbiddenKeys(child, keyPath)];
  });
}

function requireString(
  obj: Record<string, unknown>,
  path: string,
  errors: string[],
): void {
  const parts = path.split('.');
  let cur: unknown = obj;
  for (const part of parts) {
    if (!isObject(cur)) {
      errors.push(`Missing required field: ${path}`);
      return;
    }
    cur = cur[part];
  }
  if (typeof cur !== 'string' || cur.length === 0) {
    errors.push(`Missing or empty required field: ${path}`);
  }
}

export function parsePackageJson(text: string): { data?: unknown; error?: string } {
  try {
    return { data: JSON.parse(text) };
  } catch (e) {
    return { error: e instanceof Error ? e.message : 'Invalid JSON' };
  }
}

export function validateFailurePackage(input: unknown): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  if (!isObject(input)) {
    return {
      valid: false,
      errors: ['Package must be a JSON object.'],
      warnings,
      forbiddenFields: [],
    };
  }

  const forbiddenFields = findForbiddenKeys(input);
  if (forbiddenFields.length > 0) {
    errors.push(
      'Package contains private QA-oracle fields. These are stripped from AI evidence and must not be submitted.',
    );
  }

  requireString(input, 'schema_version', errors);
  requireString(input, 'source', errors);
  requireString(input, 'run.run_id', errors);
  requireString(input, 'repository.name', errors);
  requireString(input, 'repository.branch', errors);
  requireString(input, 'repository.commit_sha', errors);
  requireString(input, 'environment.name', errors);
  requireString(input, 'environment.browser', errors);
  requireString(input, 'test.name', errors);
  requireString(input, 'test.file', errors);
  requireString(input, 'failure.message', errors);

  if (isObject(input) && input.schema_version !== '1.0' && typeof input.schema_version === 'string') {
    warnings.push(`Unrecognized schema_version "${input.schema_version}" — expected "1.0".`);
  }

  const test = isObject(input.test) ? input.test : undefined;
  if (test && test.status !== 'failed') {
    warnings.push(`test.status is "${String(test.status)}" — TriageZero investigates failed tests.`);
  }

  if (!Array.isArray((input as Record<string, unknown>).network_evidence)) {
    warnings.push('No network_evidence array — network analysis will be limited.');
  }
  if (!Array.isArray((input as Record<string, unknown>).console_errors)) {
    warnings.push('No console_errors array — console analysis will be limited.');
  }
  if (!isObject((input as Record<string, unknown>).artifacts)) {
    warnings.push('No artifacts object — screenshot/trace review unavailable.');
  }

  const valid = errors.length === 0;
  return {
    valid,
    errors,
    warnings,
    forbiddenFields,
    pkg: valid ? (input as unknown as FailurePackage) : undefined,
  };
}
