import assert from 'node:assert';
import test from 'node:test';
import {
  formatSpecialistName,
  parseFindingsParagraphs,
  extractInvalidChunkIds,
  getStatusDisplay,
  formatTelemetryData,
  formatSpecialistOutcome,
  extractSpecialistEntries
} from '../src/services/responseFormatter.ts';
import type { AnalysisResponse } from '../src/types/api.ts';

test('1. formatSpecialistName formats all known and custom specialist agent keys', () => {
  assert.strictEqual(formatSpecialistName('trial_data_analyst'), 'Trial Data Analyst');
  assert.strictEqual(formatSpecialistName('literature_research'), 'Literature Research (RAG)');
  assert.strictEqual(formatSpecialistName('compound_similarity'), 'Compound Similarity');
  assert.strictEqual(formatSpecialistName('similarity_agent'), 'Compound Similarity');
  assert.strictEqual(formatSpecialistName('adverse_event_triage'), 'Adverse Event Triage');
  assert.strictEqual(formatSpecialistName('report_writer'), 'Report Writer');
  assert.strictEqual(formatSpecialistName('custom_trial_agent'), 'Custom Trial Agent');
});

test('2. parseFindingsParagraphs handles multi-paragraph text and empty/null inputs safely', () => {
  const multi = 'First paragraph describing trial metrics.\n\nSecond paragraph describing safety findings.';
  const paras = parseFindingsParagraphs(multi);
  assert.strictEqual(paras.length, 2);
  assert.strictEqual(paras[0], 'First paragraph describing trial metrics.');
  assert.strictEqual(paras[1], 'Second paragraph describing safety findings.');

  // Single paragraph
  const single = 'Single unified finding summary.';
  assert.deepStrictEqual(parseFindingsParagraphs(single), ['Single unified finding summary.']);

  // Empty, whitespace, null, undefined
  assert.deepStrictEqual(parseFindingsParagraphs(''), []);
  assert.deepStrictEqual(parseFindingsParagraphs('   \n\n   '), []);
  assert.deepStrictEqual(parseFindingsParagraphs(null), []);
  assert.deepStrictEqual(parseFindingsParagraphs(undefined), []);
});

test('3. extractInvalidChunkIds extracts and deduplicates unverified citation chunk IDs', () => {
  const citations = [
    {
      claim: 'Claim A',
      citations: ['chunk-01', 'chunk-02'],
      invalid_chunk_ids: ['chunk-invalid-99', 'chunk-invalid-88']
    },
    {
      claim: 'Claim B',
      citations: ['chunk-03'],
      invalid_chunk_ids: ['chunk-invalid-99'] // duplicate ID
    },
    {
      claim: 'Claim C',
      citations: ['chunk-04'],
      invalid_chunk_ids: []
    }
  ];

  const invalidIds = extractInvalidChunkIds(citations);
  assert.strictEqual(invalidIds.length, 2);
  assert.deepStrictEqual(invalidIds, ['chunk-invalid-99', 'chunk-invalid-88']);

  // Edge cases
  assert.deepStrictEqual(extractInvalidChunkIds([]), []);
  assert.deepStrictEqual(extractInvalidChunkIds(null), []);
});

test('4. getStatusDisplay maps all 5 lifecycle states to truthful labels and distinct classes', () => {
  const success = getStatusDisplay('success');
  assert.strictEqual(success.label, 'Analysis Completed');
  assert.strictEqual(success.badgeClass, 'success');
  assert.strictEqual(success.isSuccess, true);
  assert.strictEqual(success.isRefusal, false);

  const partial = getStatusDisplay('partial_success');
  assert.strictEqual(partial.label, 'Partial Success');
  assert.strictEqual(partial.badgeClass, 'partial_success');
  assert.strictEqual(partial.isPartial, true);
  assert.strictEqual(partial.isSuccess, false);

  const refusal = getStatusDisplay('guardrail_refusal');
  assert.strictEqual(refusal.label, 'Guardrail Safety Refusal');
  assert.strictEqual(refusal.badgeClass, 'guardrail_refusal');
  assert.strictEqual(refusal.isRefusal, true);
  assert.strictEqual(refusal.isSuccess, false);

  const noEvidence = getStatusDisplay('no_evidence');
  assert.strictEqual(noEvidence.label, 'No Evidence Identified');
  assert.strictEqual(noEvidence.badgeClass, 'no_evidence');
  assert.strictEqual(noEvidence.isNoEvidence, true);
  assert.strictEqual(noEvidence.isSuccess, false);

  const failed = getStatusDisplay('failed');
  assert.strictEqual(failed.label, 'Analysis Failed');
  assert.strictEqual(failed.badgeClass, 'failed');
  assert.strictEqual(failed.isFailed, true);
  assert.strictEqual(failed.isSuccess, false);
});

test('5. formatTelemetryData displays timing, tokens, and escalation only when genuine data exists', () => {
  // Case A: Full valid telemetry
  const fullMeta: AnalysisResponse = {
    status: 'success',
    findings: 'Test',
    citations: [],
    limitations: [],
    branch_outcomes: {},
    escalation_reference: 'task_ae_44910',
    timing_sec: 2.3456,
    total_tokens: 1840,
    error_message: null
  };
  const fullRes = formatTelemetryData(fullMeta);
  assert.strictEqual(fullRes.latencyStr, '2.35s');
  assert.strictEqual(fullRes.tokensStr, '1,840');
  assert.strictEqual(fullRes.escalationRef, 'task_ae_44910');
  assert.strictEqual(fullRes.hasTelemetry, true);

  // Case B: Null/missing metadata - does NOT fabricate 0s or placeholder values
  const emptyMeta: AnalysisResponse = {
    status: 'success',
    findings: 'Test',
    citations: [],
    limitations: [],
    branch_outcomes: {},
    escalation_reference: null,
    timing_sec: null,
    total_tokens: null,
    error_message: null
  };
  const emptyRes = formatTelemetryData(emptyMeta);
  assert.strictEqual(emptyRes.latencyStr, null);
  assert.strictEqual(emptyRes.tokensStr, null);
  assert.strictEqual(emptyRes.escalationRef, null);
  assert.strictEqual(emptyRes.hasTelemetry, false);

  // Case C: Tokens = 0 (e.g. offline mode) should be suppressed rather than displaying "Tokens: 0"
  const zeroTokenMeta: AnalysisResponse = {
    ...emptyMeta,
    timing_sec: 0.15,
    total_tokens: 0
  };
  const zeroRes = formatTelemetryData(zeroTokenMeta);
  assert.strictEqual(zeroRes.latencyStr, '0.15s');
  assert.strictEqual(zeroRes.tokensStr, null, 'Must NOT display 0 tokens as valid count');
  assert.strictEqual(zeroRes.hasTelemetry, true);
});

test('6. formatSpecialistOutcome safely formats string, object, array, and empty payloads', () => {
  // A. Plain string outcome
  const strRes = formatSpecialistOutcome('Filtered 14 trials, found 2 matches.');
  assert.strictEqual(strRes.text, 'Filtered 14 trials, found 2 matches.');
  assert.strictEqual(strRes.isEmpty, false);

  // B. JSON formatted string
  const jsonStrRes = formatSpecialistOutcome(
    JSON.stringify({ summary: 'Matched 3 documents', query_time_ms: 45 })
  );
  assert.strictEqual(jsonStrRes.leadSummary, 'Matched 3 documents');
  assert.strictEqual(jsonStrRes.attributes?.length, 1);
  assert.strictEqual(jsonStrRes.attributes?.[0].key, 'query time ms');
  assert.strictEqual(jsonStrRes.attributes?.[0].value, '45');

  // C. Object outcome with summary and structured fields
  const objRes = formatSpecialistOutcome({
    summary: 'AE Triage evaluated 1 event.',
    seriousness: 'Serious',
    triage_action: 'Escalate to Medical Director',
    count: 1
  });
  assert.strictEqual(objRes.leadSummary, 'AE Triage evaluated 1 event.');
  assert.strictEqual(objRes.attributes?.length, 3);
  assert.deepStrictEqual(objRes.attributes?.[0], { key: 'seriousness', value: 'Serious' });

  // D. Array outcome
  const arrRes = formatSpecialistOutcome(['DKU-1042', 'DKU-2091', 'DKU-3011']);
  assert.strictEqual(arrRes.listItems?.length, 3);
  assert.strictEqual(arrRes.isEmpty, false);

  // E. Empty / null / undefined outcomes
  assert.strictEqual(formatSpecialistOutcome('').isEmpty, true);
  assert.strictEqual(formatSpecialistOutcome({}).isEmpty, true);
  assert.strictEqual(formatSpecialistOutcome([]).isEmpty, true);
  assert.strictEqual(formatSpecialistOutcome(null).isEmpty, true);
  assert.strictEqual(formatSpecialistOutcome(undefined).isEmpty, true);
});

test('7. extractSpecialistEntries displays only present specialists without inventing absent agents', () => {
  const branchOutcomes = {
    trial_data_analyst: 'Evaluated 4 Phase III trials.',
    literature_research: 'Retrieved 3 internal whitepapers on JAK2.'
  };

  const entries = extractSpecialistEntries(branchOutcomes);
  assert.strictEqual(entries.length, 2);
  assert.strictEqual(entries[0].name, 'trial_data_analyst');
  assert.strictEqual(entries[0].label, 'Trial Data Analyst');
  assert.strictEqual(entries[1].name, 'literature_research');
  assert.strictEqual(entries[1].label, 'Literature Research (RAG)');

  // Must not contain agents that did not run
  const names = entries.map((e) => e.name);
  assert.strictEqual(names.includes('compound_similarity'), false);
  assert.strictEqual(names.includes('adverse_event_triage'), false);
  assert.strictEqual(names.includes('report_writer'), false);

  // Empty / null handling
  assert.deepStrictEqual(extractSpecialistEntries({}), []);
  assert.deepStrictEqual(extractSpecialistEntries(null), []);
  assert.deepStrictEqual(extractSpecialistEntries(undefined), []);
});
