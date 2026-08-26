/**
 * Guards the Node runtime requirement.
 *
 * The upgraded frontend toolchain (jsdom 30 / Undici) needs Node APIs that do
 * not exist on Node 20: there the suite fails while loading, before any test
 * runs. `engine-strict=true` in .npmrc makes `npm ci` refuse an unsupported
 * runtime, and this test is the second line of defence — it fails loudly with
 * an actionable message if the suite is somehow executed on one.
 *
 * Deliberately dependency-free: a minimal comparator instead of pulling in semver.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// vitest runs with the project root as cwd
const repoRoot = process.cwd();

function readText(file: string): string {
  return readFileSync(join(repoRoot, file), 'utf8').trim();
}

type Version = [number, number, number];

function parseVersion(value: string): Version {
  const [major, minor, patch] = value
    .replace(/^v/, '')
    .split('.')
    .map((part) => Number.parseInt(part, 10));
  return [major, minor ?? 0, patch ?? 0];
}

function compare(a: Version, b: Version): number {
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return 0;
}

/** Supports the comparator forms used in our engines range: `^x.y.z` and `>=x.y.z`. */
function satisfies(version: Version, range: string): boolean {
  return range.split('||').some((clause) => {
    const trimmed = clause.trim();
    if (trimmed.startsWith('^')) {
      const min = parseVersion(trimmed.slice(1));
      const nextMajor: Version = [min[0] + 1, 0, 0];
      return compare(version, min) >= 0 && compare(version, nextMajor) < 0;
    }
    if (trimmed.startsWith('>=')) {
      return compare(version, parseVersion(trimmed.slice(2))) >= 0;
    }
    return compare(version, parseVersion(trimmed)) === 0;
  });
}

const pkg = JSON.parse(readText('package.json')) as {
  engines?: { node?: string };
};
const range = pkg.engines?.node ?? '';

describe('Node runtime requirement', () => {
  it('declares a node engines range in package.json', () => {
    expect(range).toBeTruthy();
  });

  it('runs on a Node version that satisfies engines.node', () => {
    const current = parseVersion(process.version);
    expect(
      satisfies(current, range),
      `This suite is running on Node ${process.version}, which does not satisfy ` +
        `engines.node "${range}". Node 20 is not supported — the jsdom/Undici ` +
        `stack fails before tests execute. Run \`nvm use\` (see .nvmrc) and \`npm ci\`.`,
    ).toBe(true);
  });

  it('pins the same reproducible version in .nvmrc and .node-version', () => {
    const nvmrc = readText('.nvmrc');
    expect(readText('.node-version')).toBe(nvmrc);
    expect(satisfies(parseVersion(nvmrc), range)).toBe(true);
  });

  it('enables engine-strict so an unsupported runtime fails at install time', () => {
    expect(readText('.npmrc')).toMatch(/^engine-strict\s*=\s*true$/m);
  });

  it('rejects Node 20 and accepts the pinned runtime', () => {
    expect(satisfies(parseVersion('20.19.5'), range)).toBe(false);
    expect(satisfies(parseVersion('22.23.2'), range)).toBe(true);
  });
});
