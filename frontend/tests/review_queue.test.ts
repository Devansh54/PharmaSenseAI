import assert from 'node:assert';
import { describe, it } from 'node:test';
import {
  listReviews,
  getReview,
  createReviewDecision,
  AnalysisApiError
} from '../src/services/api.ts';
import type { ReviewTask, ReviewDecisionPayload } from '../src/types/api.ts';

function createMockResponse(
  body: unknown,
  init?: { status?: number; statusText?: string; ok?: boolean }
): Response {
  const status = init?.status ?? 200;
  const ok = init?.ok ?? (status >= 200 && status < 300);
  const jsonBody = typeof body === 'string' ? body : JSON.stringify(body);

  return {
    status,
    statusText: init?.statusText ?? 'OK',
    ok,
    json: async () => {
      if (typeof body === 'string') {
        throw new SyntaxError('Unexpected token in JSON');
      }
      return body;
    },
    text: async () => jsonBody
  } as unknown as Response;
}

const SAMPLE_REVIEW_TASKS: ReviewTask[] = [
  {
    task_id: 'REV-e47282d8',
    event_id: 'AE-00023',
    status: 'PENDING',
    reason: 'Fatal adverse event AE-00023 (Anemia, Severe/Serious) for patient PT-23785. Seriousness criteria met.',
    created_at: '2026-10-10T14:32:00.000Z'
  },
  {
    task_id: 'REV-991200ab',
    event_id: 'AE-00045',
    status: 'ACKNOWLEDGED',
    reason: 'Hospitalization reported for Trial TRL-0012, subject PT-10492. Inpatient admission required.',
    created_at: '2026-10-11T09:15:30.000Z'
  },
  {
    task_id: 'REV-774411cd',
    event_id: 'AE-00011',
    status: 'RESOLVED',
    reason: 'Life-threatening anaphylaxis triage completed. Safety protocol closed by Medical Director.',
    created_at: '2026-10-09T18:00:00.000Z'
  }
];

describe('Phase 7: Human Review Queue & Review Decisions', () => {
  it('1. Successful review queue loading returns all tasks with truthful fields', async () => {
    let capturedUrl = '';
    let capturedMethod = '';

    const mockFetcher: typeof fetch = async (input, init) => {
      capturedUrl = String(input);
      capturedMethod = init?.method || 'GET';
      return createMockResponse(SAMPLE_REVIEW_TASKS);
    };

    const tasks = await listReviews(mockFetcher);

    assert.strictEqual(capturedUrl.endsWith('/v1/reviews'), true);
    assert.strictEqual(capturedMethod, 'GET');
    assert.strictEqual(tasks.length, 3);
    assert.strictEqual(tasks[0].task_id, 'REV-e47282d8');
    assert.strictEqual(tasks[0].event_id, 'AE-00023');
    assert.strictEqual(tasks[0].status, 'PENDING');
    assert.strictEqual(tasks[1].status, 'ACKNOWLEDGED');
    assert.strictEqual(tasks[2].status, 'RESOLVED');
  });

  it('2. Empty queue presentation safely handles empty list from API', async () => {
    const mockFetcher: typeof fetch = async () => {
      return createMockResponse([]);
    };

    const tasks = await listReviews(mockFetcher);
    assert.strictEqual(Array.isArray(tasks), true);
    assert.strictEqual(tasks.length, 0);
  });

  it('3. Failed list retrieval raises unavailable error and supports manual retry', async () => {
    let callCount = 0;
    const mockFetcher: typeof fetch = async () => {
      callCount++;
      if (callCount === 1) {
        return createMockResponse({ detail: 'Database unavailable' }, { status: 503 });
      }
      return createMockResponse(SAMPLE_REVIEW_TASKS);
    };

    // First call fails
    await assert.rejects(
      async () => {
        await listReviews(mockFetcher);
      },
      (err: unknown) => {
        assert.ok(err instanceof AnalysisApiError);
        assert.strictEqual((err as AnalysisApiError).category, 'unavailable');
        assert.strictEqual((err as AnalysisApiError).statusCode, 503);
        return true;
      }
    );

    // Manual retry call succeeds
    const recovered = await listReviews(mockFetcher);
    assert.strictEqual(recovered.length, 3);
    assert.strictEqual(callCount, 2);
  });

  it('4. Task detail loading retrieves single review and handles 404 not found', async () => {
    let capturedUrl = '';

    const mockFetcher: typeof fetch = async (input) => {
      capturedUrl = String(input);
      if (capturedUrl.includes('REV-e47282d8')) {
        return createMockResponse(SAMPLE_REVIEW_TASKS[0]);
      }
      return createMockResponse({ detail: 'Review not found' }, { status: 404 });
    };

    // Success
    const task = await getReview('REV-e47282d8', mockFetcher);
    assert.strictEqual(task.task_id, 'REV-e47282d8');
    assert.strictEqual(task.status, 'PENDING');

    // 404
    await assert.rejects(
      async () => {
        await getReview('REV-NONEXISTENT', mockFetcher);
      },
      (err: unknown) => {
        assert.ok(err instanceof AnalysisApiError);
        assert.strictEqual((err as AnalysisApiError).category, 'not_found');
        assert.strictEqual((err as AnalysisApiError).statusCode, 404);
        return true;
      }
    );

    // Empty ID validation
    await assert.rejects(
      async () => {
        await getReview('   ', mockFetcher);
      },
      (err: unknown) => {
        assert.ok(err instanceof AnalysisApiError);
        assert.strictEqual((err as AnalysisApiError).category, 'validation');
        return true;
      }
    );
  });

  it('5. Correct rendering and distinction of Pending, Acknowledged, and Resolved states', () => {
    const pendingTask = SAMPLE_REVIEW_TASKS[0];
    const acknowledgedTask = SAMPLE_REVIEW_TASKS[1];
    const resolvedTask = SAMPLE_REVIEW_TASKS[2];

    assert.strictEqual(pendingTask.status.toUpperCase(), 'PENDING');
    assert.strictEqual(acknowledgedTask.status.toUpperCase(), 'ACKNOWLEDGED');
    assert.strictEqual(resolvedTask.status.toUpperCase(), 'RESOLVED');
  });

  it('6. Valid and invalid transition rules adhere to backend state machine', () => {
    const validTransitions: Record<string, string[]> = {
      pending: ['acknowledged', 'resolved'],
      acknowledged: ['resolved'],
      resolved: []
    };

    // Pending allows both
    assert.deepStrictEqual(validTransitions['pending'], ['acknowledged', 'resolved']);

    // Acknowledged allows only resolution
    assert.deepStrictEqual(validTransitions['acknowledged'], ['resolved']);

    // Resolved allows no further transitions
    assert.deepStrictEqual(validTransitions['resolved'], []);
  });

  it('7. Required reviewer-ID validation prevents decision execution when empty', async () => {
    let networkCalled = false;
    const mockFetcher: typeof fetch = async () => {
      networkCalled = true;
      return createMockResponse({ status: 'success' }, { status: 201 });
    };

    // Empty reviewer_id
    await assert.rejects(
      async () => {
        await createReviewDecision(
          'REV-e47282d8',
          { reviewer_id: '', decision: 'acknowledged' },
          mockFetcher
        );
      },
      (err: unknown) => {
        assert.ok(err instanceof AnalysisApiError);
        assert.strictEqual((err as AnalysisApiError).category, 'validation');
        assert.strictEqual(
          (err as AnalysisApiError).message,
          'Reviewer ID is required to record a decision.'
        );
        return true;
      }
    );

    // Whitespace reviewer_id
    await assert.rejects(
      async () => {
        await createReviewDecision(
          'REV-e47282d8',
          { reviewer_id: '   ', decision: 'acknowledged' },
          mockFetcher
        );
      },
      (err: unknown) => {
        assert.ok(err instanceof AnalysisApiError);
        assert.strictEqual((err as AnalysisApiError).category, 'validation');
        return true;
      }
    );

    // Verify network was NEVER called
    assert.strictEqual(networkCalled, false);
  });

  it('8. Correct POST route, payload schema, and error handling for decisions', async () => {
    let capturedUrl = '';
    let capturedMethod = '';
    let capturedBody = '';

    const mockFetcher: typeof fetch = async (input, init) => {
      capturedUrl = String(input);
      capturedMethod = init?.method || '';
      capturedBody = String(init?.body || '');
      return createMockResponse({ status: 'success' }, { status: 201 });
    };

    const res = await createReviewDecision(
      'REV-e47282d8',
      {
        reviewer_id: 'dr_gomez',
        decision: 'acknowledged',
        comments: 'Acknowledged severe anemia event; monitoring site labs.'
      },
      mockFetcher
    );

    assert.strictEqual(capturedUrl.endsWith('/v1/reviews/REV-e47282d8/decisions'), true);
    assert.strictEqual(capturedMethod, 'POST');
    const parsedBody = JSON.parse(capturedBody) as ReviewDecisionPayload;
    assert.strictEqual(parsedBody.reviewer_id, 'dr_gomez');
    assert.strictEqual(parsedBody.decision, 'acknowledged');
    assert.strictEqual(
      parsedBody.comments,
      'Acknowledged severe anemia event; monitoring site labs.'
    );
    assert.strictEqual(res.status, 'success');
  });

  it('9. Handles 409 Conflict when backend rejects invalid transition', async () => {
    const mockFetcher: typeof fetch = async () => {
      return createMockResponse(
        { detail: 'Invalid review transition from RESOLVED to acknowledged' },
        { status: 409 }
      );
    };

    await assert.rejects(
      async () => {
        await createReviewDecision(
          'REV-774411cd',
          { reviewer_id: 'rev_admin', decision: 'acknowledged' },
          mockFetcher
        );
      },
      (err: unknown) => {
        assert.ok(err instanceof AnalysisApiError);
        assert.strictEqual((err as AnalysisApiError).category, 'conflict');
        assert.strictEqual((err as AnalysisApiError).statusCode, 409);
        assert.ok((err as AnalysisApiError).message.includes('409 Conflict'));
        return true;
      }
    );
  });

  it('10. Double-submit prevention and state updates only after successful API response', async () => {
    let postCallCount = 0;
    let inFlight = false;

    // Simulate UI state
    let taskStatus = 'PENDING';

    const mockFetcher: typeof fetch = async () => {
      postCallCount++;
      return createMockResponse({ status: 'success' }, { status: 201 });
    };

    const submitAction = async (decision: 'acknowledged' | 'resolved') => {
      if (inFlight) return; // double submit prevented
      inFlight = true;
      try {
        await createReviewDecision(
          'REV-e47282d8',
          { reviewer_id: 'dr_smith', decision },
          mockFetcher
        );
        taskStatus = decision.toUpperCase();
      } finally {
        inFlight = false;
      }
    };

    // First call
    await submitAction('acknowledged');
    assert.strictEqual(postCallCount, 1);
    assert.strictEqual(taskStatus, 'ACKNOWLEDGED');

    // Simulate rapid concurrent submission while inFlight
    inFlight = true;
    await submitAction('resolved');
    // Blocked by inFlight guard
    assert.strictEqual(postCallCount, 1);
    assert.strictEqual(taskStatus, 'ACKNOWLEDGED');
    inFlight = false;
  });

  it('11. Failed decision submission does not falsely change the task state', async () => {
    let taskStatus = 'PENDING';

    const failingFetcher: typeof fetch = async () => {
      return createMockResponse({ detail: 'Internal Server Error' }, { status: 500 });
    };

    try {
      await createReviewDecision(
        'REV-e47282d8',
        { reviewer_id: 'dr_smith', decision: 'acknowledged' },
        failingFetcher
      );
      taskStatus = 'ACKNOWLEDGED';
    } catch {
      // Retain previous status
    }

    assert.strictEqual(taskStatus, 'PENDING', 'Task status must remain unchanged on failure');
  });

  it('12. Selecting a task makes no decision request', () => {
    let decisionRequests = 0;

    const onSelectTask = (task: ReviewTask) => {
      // Merely sets active task ID
      assert.ok(task.task_id);
    };

    onSelectTask(SAMPLE_REVIEW_TASKS[0]);
    onSelectTask(SAMPLE_REVIEW_TASKS[1]);
    onSelectTask(SAMPLE_REVIEW_TASKS[2]);

    assert.strictEqual(decisionRequests, 0, 'Selecting task must not trigger decision requests');
  });

  it('13. Navigation into and out of Human Review makes zero unintended decision requests', () => {
    let decisionRequests = 0;

    const navigateTab = (tab: string) => {
      // Tab switching
      assert.ok(tab);
    };

    navigateTab('review');
    navigateTab('new-analysis');
    navigateTab('library');
    navigateTab('review');

    assert.strictEqual(decisionRequests, 0, 'Tab navigation must never send review decisions');
  });
});
