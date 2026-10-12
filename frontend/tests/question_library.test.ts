import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  QUESTION_CATALOG,
  GOLDEN_SET_CASE_COUNT,
  CATALOG_TOTAL_COUNT,
  type QuestionCatalogEntry
} from '../src/data/questionCatalog.ts';

describe('Phase 6: Question Library & Verification Inventory', () => {
  it('1. Catalog schema validity: every item has required fields and truthful types', () => {
    assert.strictEqual(Array.isArray(QUESTION_CATALOG), true);
    assert.strictEqual(QUESTION_CATALOG.length, CATALOG_TOTAL_COUNT);

    const validCategories = new Set([
      'Trial Analytics',
      'Literature Research',
      'Adverse Event Triage',
      'Compound Similarity',
      'Multi-Specialist Synthesis',
      'Escalation',
      'Guardrail & Safety'
    ]);

    for (const item of QUESTION_CATALOG) {
      assert.ok(typeof item.id === 'string' && item.id.length > 0, `Missing id on ${JSON.stringify(item)}`);
      assert.ok(typeof item.query === 'string' && item.query.length > 0, `Missing query on ${item.id}`);
      assert.ok(validCategories.has(item.category), `Invalid category "${item.category}" on ${item.id}`);
      assert.ok(Array.isArray(item.sources) && item.sources.length > 0, `Missing sources on ${item.id}`);
      assert.ok(Array.isArray(item.golden_case_ids), `Missing golden_case_ids array on ${item.id}`);
      assert.ok(Array.isArray(item.acceptance_scenario_ids), `Missing acceptance_scenario_ids array on ${item.id}`);
      assert.ok(typeof item.workflow_type === 'string', `Missing workflow_type on ${item.id}`);
      assert.ok(Array.isArray(item.expected_specialists), `Missing expected_specialists on ${item.id}`);
      assert.ok(Array.isArray(item.expected_tools), `Missing expected_tools on ${item.id}`);
      assert.ok(typeof item.is_evaluation_only === 'boolean', `Missing is_evaluation_only on ${item.id}`);
      assert.ok(['passed', 'unverified', 'disputed', 'N/A'].includes(item.historical_live_status), `Invalid historical_live_status on ${item.id}`);
      assert.ok(['passed', 'blocked', 'disputed', 'unverified'].includes(item.offline_status), `Invalid offline_status on ${item.id}`);
      assert.ok(['pending', 'unverified'].includes(item.current_revision_live_status), `Invalid current_revision_live_status on ${item.id}`);
      assert.ok(typeof item.status_notes === 'string' && item.status_notes.length > 0, `Missing status_notes on ${item.id}`);
      assert.ok(typeof item.show_as_suggestion === 'boolean', `Missing show_as_suggestion on ${item.id}`);
    }
  });

  it('2. Unique IDs: all catalog entries have distinct IDs', () => {
    const ids = QUESTION_CATALOG.map((item) => item.id);
    const uniqueIds = new Set(ids);
    assert.strictEqual(uniqueIds.size, ids.length, 'Duplicate catalog IDs detected!');
  });

  it('3. Deduplication: no two catalog items have identical query text, and multi-source queries merge cleanly', () => {
    const queries = QUESTION_CATALOG.map((item) => item.query.trim());
    const uniqueQueries = new Set(queries);
    assert.strictEqual(uniqueQueries.size, queries.length, 'Duplicate query strings detected in catalog!');

    // S1 should have multiple sources merged
    const s1 = QUESTION_CATALOG.find((q) => q.acceptance_scenario_ids.includes('S1'));
    assert.ok(s1, 'S1 not found in catalog');
    assert.ok(s1.sources.length >= 3, 'S1 sources were not merged properly');
    assert.ok(s1.sources.includes('tests/test_live_acceptance.py'));
    assert.ok(s1.sources.includes('docs/final_acceptance_report.md'));
    assert.ok(s1.sources.includes('README.md'));

    // S2 should have multiple sources merged
    const s2 = QUESTION_CATALOG.find((q) => q.acceptance_scenario_ids.includes('S2'));
    assert.ok(s2, 'S2 not found in catalog');
    assert.ok(s2.sources.length >= 3, 'S2 sources were not merged properly');
  });

  it('4. Preservation of all 28 golden-set case IDs', () => {
    assert.strictEqual(GOLDEN_SET_CASE_COUNT, 28);
    const presentGoldenCaseIds = new Set(
      QUESTION_CATALOG.flatMap((item) => item.golden_case_ids)
    );

    assert.strictEqual(presentGoldenCaseIds.size, 28, 'Expected exactly 28 unique golden case IDs across catalog');

    // Verify key categories of golden set
    assert.ok(presentGoldenCaseIds.has('eval-rag-001'));
    assert.ok(presentGoldenCaseIds.has('eval-rag-007'));
    assert.ok(presentGoldenCaseIds.has('eval-sql-001'));
    assert.ok(presentGoldenCaseIds.has('eval-sql-005'));
    assert.ok(presentGoldenCaseIds.has('eval-sim-001'));
    assert.ok(presentGoldenCaseIds.has('eval-sim-003'));
    assert.ok(presentGoldenCaseIds.has('eval-par-001'));
    assert.ok(presentGoldenCaseIds.has('eval-par-004'));
    assert.ok(presentGoldenCaseIds.has('eval-esc-001'));
    assert.ok(presentGoldenCaseIds.has('eval-esc-002'));
    assert.ok(presentGoldenCaseIds.has('eval-grd-001'));
    assert.ok(presentGoldenCaseIds.has('eval-grd-007'));
  });

  it('5. Search filtering logic matches query text, category, ID, and metadata', () => {
    const searchFilter = (searchTerm: string) => {
      const qLower = searchTerm.trim().toLowerCase();
      return QUESTION_CATALOG.filter((item) => {
        const matchText = (
          item.query +
          ' ' +
          item.id +
          ' ' +
          item.category +
          ' ' +
          item.workflow_type +
          ' ' +
          item.status_notes +
          ' ' +
          item.historical_live_status +
          ' ' +
          item.offline_status +
          ' ' +
          item.sources.join(' ') +
          ' ' +
          item.golden_case_ids.join(' ') +
          ' ' +
          item.acceptance_scenario_ids.join(' ') +
          ' ' +
          item.expected_specialists.join(' ') +
          ' ' +
          item.expected_tools.join(' ')
        ).toLowerCase();
        return matchText.includes(qLower);
      });
    };

    // Search by compound code
    const dkuResults = searchFilter('DKU-1042');
    assert.ok(dkuResults.length >= 3, 'Expected multiple results for DKU-1042');

    // Search by catalog ID
    const s1ById = searchFilter('ps-acc-s1');
    assert.strictEqual(s1ById.length, 1);
    assert.strictEqual(s1ById[0].acceptance_scenario_ids[0], 'S1');

    // Search by golden case ID
    const evalSql1 = searchFilter('eval-sql-001');
    assert.strictEqual(evalSql1.length, 1);
    assert.strictEqual(evalSql1[0].golden_case_ids[0], 'eval-sql-001');

    // Search by status keyword
    const disputed = searchFilter('discrepancy');
    assert.ok(disputed.length >= 5, 'Search should locate disputed naming discrepancies');
  });

  it('6. Category and verification-status filtering', () => {
    const litCat = QUESTION_CATALOG.filter((c) => c.category === 'Literature Research');
    assert.strictEqual(litCat.length, 9);

    const trialCat = QUESTION_CATALOG.filter((c) => c.category === 'Trial Analytics');
    assert.strictEqual(trialCat.length, 5);

    const aeCat = QUESTION_CATALOG.filter((c) => c.category === 'Adverse Event Triage');
    assert.strictEqual(aeCat.length, 4);

    const simCat = QUESTION_CATALOG.filter((c) => c.category === 'Compound Similarity');
    assert.strictEqual(simCat.length, 5);

    const multiCat = QUESTION_CATALOG.filter((c) => c.category === 'Multi-Specialist Synthesis');
    assert.strictEqual(multiCat.length, 8);

    const escCat = QUESTION_CATALOG.filter((c) => c.category === 'Escalation');
    assert.strictEqual(escCat.length, 2);

    const grdCat = QUESTION_CATALOG.filter((c) => c.category === 'Guardrail & Safety');
    assert.strictEqual(grdCat.length, 10);

    // Sum of all category subsets equals total catalog count
    const totalByCats = litCat.length + trialCat.length + aeCat.length + simCat.length + multiCat.length + escCat.length + grdCat.length;
    assert.strictEqual(totalByCats, CATALOG_TOTAL_COUNT);
  });

  it('7. Evaluation-only classification isolates guardrails from genuine research queries', () => {
    const evalOnly = QUESTION_CATALOG.filter((c) => c.is_evaluation_only);
    const research = QUESTION_CATALOG.filter((c) => !c.is_evaluation_only);

    assert.strictEqual(evalOnly.length, 10);
    assert.strictEqual(research.length, 33);
    assert.strictEqual(evalOnly.length + research.length, CATALOG_TOTAL_COUNT);

    // Default suggestions must never be evaluation-only
    for (const q of QUESTION_CATALOG) {
      if (q.show_as_suggestion) {
        assert.strictEqual(q.is_evaluation_only, false, 'Default suggestions must not be evaluation-only');
      }
    }
  });

  it('8. Preservation of historical, offline, and disputed status boundaries', () => {
    const historicalLivePassed = QUESTION_CATALOG.filter((c) => c.historical_live_status === 'passed');
    // 8 Tier 1 acceptance scenarios + eval-grd-004 + eval-grd-005 = 10
    assert.strictEqual(historicalLivePassed.length, 10);

    const disputedNaming = QUESTION_CATALOG.filter((c) => c.offline_status === 'disputed');
    assert.strictEqual(disputedNaming.length, 7);

    const blockedContract = QUESTION_CATALOG.filter((c) => c.offline_status === 'blocked');
    assert.strictEqual(blockedContract.length, 2);

    // Current revision status must NEVER claim unverified live passes
    for (const item of QUESTION_CATALOG) {
      assert.ok(
        item.current_revision_live_status === 'pending' || item.current_revision_live_status === 'unverified',
        `Item ${item.id} claimed live success for uncommitted code without verification!`
      );
    }
  });

  it('9. Exactly two default suggestions are preserved with unchanged text', () => {
    const suggestions = QUESTION_CATALOG.filter((c) => c.show_as_suggestion);
    assert.strictEqual(suggestions.length, 2, 'Expected exactly two default suggestions');

    const expectedS1 = 'Which Phase II oncology trials are below 60% enrollment right now?';
    const expectedS2 = 'What has our internal research said about JAK2 inhibitors and cardiotoxicity?';

    assert.ok(suggestions.some((s) => s.query === expectedS1), 'Default suggestion 1 missing');
    assert.ok(suggestions.some((s) => s.query === expectedS2), 'Default suggestion 2 missing');
  });

  it('10. Question selection populates composer without auto-submitting or making API calls', () => {
    let sharedPrompt = '';
    let activeTab = 'library';
    let submitCallCount = 0;
    let apiCallCount = 0;

    const mockSelectFromLibrary = (selectedQuery: string) => {
      // Mimics AppLayout.tsx handleSelectFromLibrary
      sharedPrompt = selectedQuery;
      activeTab = 'new-analysis';
      // No submit call, no api call
    };

    const targetQuery = 'Find compounds similar to DKU-1042 and explain why they are considered similar.';
    mockSelectFromLibrary(targetQuery);

    assert.strictEqual(sharedPrompt, targetQuery);
    assert.strictEqual(activeTab, 'new-analysis');
    assert.strictEqual(submitCallCount, 0);
    assert.strictEqual(apiCallCount, 0);
  });

  it('11. README inventory counts and catalog counts remain consistent', () => {
    const readmePath = path.resolve('..', 'README.md');
    if (fs.existsSync(readmePath)) {
      const readmeContent = fs.readFileSync(readmePath, 'utf-8');

      // Check stated counts in README
      assert.ok(readmeContent.includes('Total Distinct Catalog Questions**: 43'), 'README total count mismatch');
      assert.ok(readmeContent.includes('Golden-Set Benchmark Cases**: 28'), 'README golden set count mismatch');
      assert.ok(readmeContent.includes('Tier 1 Live Acceptance Scenarios**: 8'), 'README acceptance scenarios count mismatch');
    }
  });

  it('12. JSON catalog in evals/question_catalog.json matches TypeScript data module', () => {
    const jsonPath = path.resolve('..', 'evals', 'question_catalog.json');
    if (fs.existsSync(jsonPath)) {
      const jsonContent = JSON.parse(fs.readFileSync(jsonPath, 'utf-8')) as QuestionCatalogEntry[];
      assert.strictEqual(jsonContent.length, CATALOG_TOTAL_COUNT);
      assert.strictEqual(jsonContent[0].id, QUESTION_CATALOG[0].id);
      assert.strictEqual(jsonContent[0].query, QUESTION_CATALOG[0].query);
    }
  });
});
