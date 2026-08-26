import { screen, within } from '@testing-library/react';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  AnalysisProvenanceCard,
  HumanResolutionCard,
  SyntheticBadge,
} from '../components/investigations/AnalysisProvenance';
import type { AiMetadata, HumanResolution, OriginalPrediction } from '../types';

const fullMeta: AiMetadata = {
  provider: 'gemini_adk',
  modelName: 'gemini-2.5-flash',
  promptVersion: 'v1',
  analysisSchemaVersion: '1.0',
  durationMs: 2400,
  inputTokens: 1234,
  outputTokens: 321,
  fallbackReason: null,
  usedFallback: false,
  requiresHumanReview: false,
  stageSummaries: [
    { stage: 'evidence_normalization', summary: 'Extracted 3 network signals.', durationMs: 12 },
    { stage: 'risk_assessment', summary: 'Policy assigned severity=critical.', durationMs: 4 },
  ],
  retrievalSignals: ['same_endpoint'],
};

describe('AI provenance panel', () => {
  it('renders provider, model, prompt version, duration and tokens', () => {
    render(<AnalysisProvenanceCard meta={fullMeta} />);
    // appears both as the header badge and in the details list
    expect(screen.getAllByText('Gemini + Google ADK').length).toBeGreaterThan(0);
    expect(screen.getByText('gemini-2.5-flash')).toBeInTheDocument();
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText('1.0')).toBeInTheDocument();
    expect(screen.getByText(/2\.4s/)).toBeInTheDocument();
    expect(screen.getByText(/1234 in · 321 out/)).toBeInTheDocument();
  });

  it('renders safe stage summaries and states that reasoning is never stored', () => {
    render(<AnalysisProvenanceCard meta={fullMeta} />);
    expect(screen.getByText('Evidence Normalization')).toBeInTheDocument();
    expect(screen.getByText('Extracted 3 network signals.')).toBeInTheDocument();
    expect(screen.getByText(/never requested, stored, or displayed/i)).toBeInTheDocument();
  });

  it('shows the fallback state visibly with its reason', () => {
    render(
      <AnalysisProvenanceCard
        meta={{
          ...fullMeta,
          provider: 'deterministic_fallback',
          usedFallback: true,
          fallbackReason: 'unconfigured',
          modelName: null,
        }}
      />,
    );
    expect(screen.getByText('Fallback used')).toBeInTheDocument();
    expect(screen.getByText(/did not run \(unconfigured\)/)).toBeInTheDocument();
    expect(screen.getByText(/no model used/)).toBeInTheDocument();
  });

  it('has a safe empty state when metadata is missing', () => {
    render(<AnalysisProvenanceCard meta={null} />);
    expect(screen.getByText(/No analysis metadata recorded/i)).toBeInTheDocument();
  });

  it('shows a safe placeholder when token usage is unavailable', () => {
    render(
      <AnalysisProvenanceCard
        meta={{ ...fullMeta, inputTokens: null, outputTokens: null }}
      />,
    );
    expect(screen.getByText(/Not reported by this provider/i)).toBeInTheDocument();
  });

  it('never renders anything resembling a credential', () => {
    const { container } = render(<AnalysisProvenanceCard meta={fullMeta} />);
    const text = container.textContent ?? '';
    expect(text).not.toMatch(/api[_-]?key/i);
    expect(text).not.toMatch(/AIza/);
    expect(text).not.toMatch(/secret/i);
  });
});

describe('Human resolution panel', () => {
  const resolution: HumanResolution = {
    classification: 'test_automation_defect',
    severity: 'medium',
    releaseRisk: 'low',
    resolutionSummary: 'Stale selector after the UI refactor.',
    responsibleComponent: 'novacart-playwright',
    resolver: 'b.radhakrishnan',
    resolvedAt: '2026-08-25T18:30:00Z',
    revision: 2,
  };
  const prediction: OriginalPrediction = {
    classification: 'backend_application_defect',
    confidence: 0.93,
    severity: 'critical',
    releaseRisk: 'block_release',
    provider: 'gemini',
  };

  it('renders the reviewed outcome', () => {
    render(<HumanResolutionCard resolution={resolution} prediction={null} />);
    expect(screen.getByText(/Stale selector/)).toBeInTheDocument();
    expect(screen.getByText('b.radhakrishnan')).toBeInTheDocument();
    expect(screen.getByText(/Reviewed · rev 2/)).toBeInTheDocument();
  });

  it('contrasts the original AI prediction with the reviewed outcome', () => {
    render(<HumanResolutionCard resolution={resolution} prediction={prediction} />);
    expect(screen.getByText(/Predicted Backend Defect/)).toBeInTheDocument();
    expect(screen.getByText('Corrected by reviewer')).toBeInTheDocument();
  });

  it('marks an agreeing review as confirmed', () => {
    render(
      <HumanResolutionCard
        resolution={resolution}
        prediction={{ ...prediction, classification: 'test_automation_defect' }}
      />,
    );
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
  });

  it('has a safe empty state when not yet reviewed', () => {
    render(<HumanResolutionCard resolution={null} prediction={null} />);
    expect(screen.getByText('Not reviewed')).toBeInTheDocument();
    expect(
      screen.getByText(/never enter the historical corpus/i),
    ).toBeInTheDocument();
  });
});

describe('Synthetic benchmark labeling', () => {
  it('labels seeded benchmark data', () => {
    const { container } = render(<SyntheticBadge />);
    expect(within(container).getByText('Synthetic benchmark')).toBeInTheDocument();
    expect(container.querySelector('[title]')?.getAttribute('title')).toMatch(
      /not a real failure/i,
    );
  });
});
