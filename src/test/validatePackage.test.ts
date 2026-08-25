import { sampleFailurePackage } from '../data/samplePackage';
import {
  FORBIDDEN_ORACLE_FIELDS,
  parsePackageJson,
  validateFailurePackage,
} from '../utils/validatePackage';

describe('failure-package validation', () => {
  it('accepts a valid package', () => {
    const result = validateFailurePackage(sampleFailurePackage);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
    expect(result.forbiddenFields).toHaveLength(0);
    expect(result.pkg?.test.name).toBe('successful checkout shows confirmation page');
  });

  it('rejects packages containing private QA-oracle fields', () => {
    const poisoned = {
      ...sampleFailurePackage,
      expected_classification: 'backend_application_defect',
      failure: {
        ...sampleFailurePackage.failure,
        private_oracle: { scenario_name: 'controlled-500' },
      },
    };
    const result = validateFailurePackage(poisoned);
    expect(result.valid).toBe(false);
    expect(result.forbiddenFields).toContain('expected_classification');
    expect(result.forbiddenFields).toContain('failure.private_oracle');
    expect(result.forbiddenFields).toContain('failure.private_oracle.scenario_name');
  });

  it('detects every forbidden oracle key, even nested', () => {
    for (const field of FORBIDDEN_ORACLE_FIELDS) {
      const result = validateFailurePackage({
        ...sampleFailurePackage,
        nested: { deeper: { [field]: true } },
      });
      expect(result.valid).toBe(false);
      expect(result.forbiddenFields.join(',')).toContain(field);
    }
  });

  it('reports missing required fields', () => {
    const result = validateFailurePackage({ schema_version: '1.0' });
    expect(result.valid).toBe(false);
    expect(result.errors.some((e) => e.includes('test.name'))).toBe(true);
    expect(result.errors.some((e) => e.includes('repository.name'))).toBe(true);
  });

  it('reports invalid JSON with a helpful parse error', () => {
    const parsed = parsePackageJson('{not json');
    expect(parsed.error).toBeTruthy();
    expect(parsed.data).toBeUndefined();
  });
});
