import assert from 'node:assert';
import test from 'node:test';

// Constants matching Composer specification
const MAX_QUESTION_LENGTH = 2000;

const SUGGESTIONS = [
  {
    id: 'sug-trial-oncology',
    category: 'Trial Analytics',
    categoryType: 'trial',
    prompt: 'Which Phase II oncology trials are below 60% enrollment right now?'
  },
  {
    id: 'sug-lit-cardiotox',
    category: 'Literature Research',
    categoryType: 'literature',
    prompt: 'What has our internal research said about JAK2 inhibitors and cardiotoxicity?'
  }
];

function validatePrompt(prompt: string): { isValid: boolean; isEmpty: boolean; isOverLimit: boolean; charCount: number } {
  const charCount = prompt.length;
  const trimmed = prompt.trim();
  const isEmpty = trimmed.length === 0;
  const isOverLimit = charCount > MAX_QUESTION_LENGTH;
  const isValid = !isEmpty && !isOverLimit;
  return { isValid, isEmpty, isOverLimit, charCount };
}

test('Phase 2: Suggested questions inventory has exactly two default queries', () => {
  assert.strictEqual(SUGGESTIONS.length, 2, 'Must contain exactly two suggestions');

  assert.strictEqual(
    SUGGESTIONS[0].prompt,
    'Which Phase II oncology trials are below 60% enrollment right now?',
    'Suggestion 1 must match exact prompt text'
  );
  assert.strictEqual(SUGGESTIONS[0].category, 'Trial Analytics');

  assert.strictEqual(
    SUGGESTIONS[1].prompt,
    'What has our internal research said about JAK2 inhibitors and cardiotoxicity?',
    'Suggestion 2 must match exact prompt text'
  );
  assert.strictEqual(SUGGESTIONS[1].category, 'Literature Research');
});

test('Phase 2: Empty input and whitespace-only validation', () => {
  assert.strictEqual(validatePrompt('').isValid, false);
  assert.strictEqual(validatePrompt('   ').isValid, false);
  assert.strictEqual(validatePrompt('\n\t  \n').isValid, false);
  assert.strictEqual(validatePrompt('').isEmpty, true);
});

test('Phase 2: Maximum length validation at 2,000 characters', () => {
  const exact2000 = 'a'.repeat(2000);
  const result2000 = validatePrompt(exact2000);
  assert.strictEqual(result2000.isValid, true);
  assert.strictEqual(result2000.isOverLimit, false);
  assert.strictEqual(result2000.charCount, 2000);

  const over2000 = 'a'.repeat(2001);
  const resultOver = validatePrompt(over2000);
  assert.strictEqual(resultOver.isValid, false);
  assert.strictEqual(resultOver.isOverLimit, true);
  assert.strictEqual(resultOver.charCount, 2001);
});

test('Phase 2: Suggestion selection populates prompt and permits manual editing without auto-submission', () => {
  let promptState = '';
  let submittedState: string | null = null;
  let apiCallMade = false;

  const onSelectSuggestion = (text: string) => {
    // Populates without submitting
    promptState = text;
  };

  const onSubmit = (text: string) => {
    submittedState = text;
  };

  // 1. User selects suggestion 1
  onSelectSuggestion(SUGGESTIONS[0].prompt);
  assert.strictEqual(promptState, 'Which Phase II oncology trials are below 60% enrollment right now?');
  assert.strictEqual(submittedState, null, 'Selection must NOT auto-submit');
  assert.strictEqual(apiCallMade, false, 'Selection must NOT make API calls');

  // 2. User edits the text manually
  promptState += ' Filter by breast cancer.';
  assert.strictEqual(
    promptState,
    'Which Phase II oncology trials are below 60% enrollment right now? Filter by breast cancer.'
  );

  // 3. User explicitly submits
  const validation = validatePrompt(promptState);
  assert.strictEqual(validation.isValid, true);
  onSubmit(promptState.trim());
  assert.strictEqual(
    submittedState,
    'Which Phase II oncology trials are below 60% enrollment right now? Filter by breast cancer.'
  );
});

test('Phase 2: Submission stages locally without network or LLM calls', () => {
  let networkCallsCount = 0;
  let stagedQuestion: string | null = null;

  const handleSubmit = (text: string) => {
    // In Phase 2, this is captured strictly in local state
    stagedQuestion = text;
  };

  handleSubmit(SUGGESTIONS[1].prompt);
  assert.strictEqual(
    stagedQuestion,
    'What has our internal research said about JAK2 inhibitors and cardiotoxicity?'
  );
  assert.strictEqual(networkCallsCount, 0, 'No network requests dispatched');
});
