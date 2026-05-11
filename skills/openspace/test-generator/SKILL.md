---
name: test-generator
description: Use when a PR adds new functions, API endpoints, or security-sensitive code without corresponding tests.
trigger: Use when a PR adds new functions, API endpoints, or security-sensitive code without corresponding tests.
tags:
- testing
- quality
- security
- review
backends:
- shell
- mcp
version: 1.0.0
lineage:
  origin: manual
  generation: 1
  parent_skill_id: null
  change_summary: Created for comprehensive test coverage
quality_metrics:
  total_selections: 0
  total_applied: 0
  total_completions: 0
  success_rate: 0.0
source_case: missing_tests

---

# Test Generator

## Risk Profile

- New code without test coverage
- Security-sensitive paths (auth, input validation, permissions) untested
- Edge cases not covered (null, empty, boundary values, overflow)
- Async operations without timeout or error tests
- API endpoints without integration tests
- Database operations without transaction rollback tests
- Missing negative test cases (invalid input, unauthorized access)

## Context Plan

1. Identify new or modified functions, classes, and API endpoints in the diff
2. Check existing test patterns and conventions (Jest, Mocha, pytest, JUnit)
3. Determine test types needed: unit (pure functions), integration (API/DB), security (malicious input)
4. Generate tests matching repository conventions (file naming, describe/it structure, assertions)
5. Cover: happy path, error cases, edge cases (null/empty/boundary), security (injection/XSS)

## Checklist

- [ ] Does each new function have unit tests covering happy path and error cases?
- [ ] Do API endpoints have integration tests with valid and invalid requests?
- [ ] Are input validation rules tested with malicious inputs (SQL injection, XSS, path traversal)?
- [ ] Are edge cases covered (null, undefined, empty string, empty array, max/min values)?
- [ ] Are async operations tested with timeouts and error scenarios?
- [ ] Do database operations have tests with transaction rollback?
- [ ] Are authentication/authorization paths tested with unauthorized access attempts?
- [ ] Do tests follow repository conventions (file naming, structure, mocking patterns)?

## Test Templates

### Unit Test (Jest/TypeScript)

```typescript
describe('getUserById', () => {
  it('returns user when ID exists', async () => {
    const user = await getUserById(1);
    expect(user).toMatchObject({ id: 1, name: expect.any(String) });
  });

  it('throws NotFoundError when ID does not exist', async () => {
    await expect(getUserById(999)).rejects.toThrow(NotFoundError);
  });

  it('rejects invalid ID types', async () => {
    await expect(getUserById('invalid')).rejects.toThrow(ValidationError);
  });

  it('handles null and undefined', async () => {
    await expect(getUserById(null)).rejects.toThrow(ValidationError);
    await expect(getUserById(undefined)).rejects.toThrow(ValidationError);
  });
});
```

### Integration Test (API endpoint)

```typescript
describe('POST /api/users', () => {
  it('creates user with valid data', async () => {
    const res = await request(app)
      .post('/api/users')
      .send({ name: 'Alice', email: 'alice@example.com' })
      .expect(201);
    expect(res.body).toMatchObject({ id: expect.any(Number), name: 'Alice' });
  });

  it('rejects duplicate email', async () => {
    await createUser({ name: 'Bob', email: 'bob@example.com' });
    await request(app)
      .post('/api/users')
      .send({ name: 'Bob2', email: 'bob@example.com' })
      .expect(409);
  });

  it('validates required fields', async () => {
    await request(app)
      .post('/api/users')
      .send({ name: 'Charlie' }) // missing email
      .expect(400);
  });

  it('rejects invalid email format', async () => {
    await request(app)
      .post('/api/users')
      .send({ name: 'Dave', email: 'not-an-email' })
      .expect(400);
  });
});
```

### Security Test (Injection protection)

```typescript
describe('SQL injection protection', () => {
  it('treats SQL syntax as literal data', async () => {
    const malicious = "'; DROP TABLE users; --";
    const user = await getUserByName(malicious);
    expect(user).toBeNull(); // Query returns no results, doesn't execute DROP
  });

  it('escapes special characters in search', async () => {
    const user = await createUser({ name: "O'Brien" });
    const found = await getUserByName("O'Brien");
    expect(found.id).toBe(user.id);
  });
});

describe('XSS protection', () => {
  it('escapes HTML in user input', async () => {
    const res = await request(app)
      .get('/profile/test')
      .query({ bio: '<script>alert(1)</script>' });
    expect(res.text).not.toContain('<script>');
    expect(res.text).toContain('&lt;script&gt;');
  });
});
```

### Edge Case Tests

```typescript
describe('edge cases', () => {
  it('handles empty array', async () => {
    const result = await processItems([]);
    expect(result).toEqual([]);
  });

  it('handles null values', async () => {
    const result = await processItem(null);
    expect(result).toBeNull();
  });

  it('handles maximum integer', async () => {
    const result = await calculateTotal(Number.MAX_SAFE_INTEGER);
    expect(result).toBeLessThanOrEqual(Number.MAX_SAFE_INTEGER);
  });

  it('handles very long strings', async () => {
    const longString = 'a'.repeat(10000);
    await expect(validateInput(longString)).rejects.toThrow(ValidationError);
  });
});
```

### Async/Timeout Tests

```typescript
describe('async operations', () => {
  it('completes within timeout', async () => {
    await expect(fetchData()).resolves.toBeDefined();
  }, 5000); // 5 second timeout

  it('handles network errors', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await expect(fetchData()).rejects.toThrow('Network error');
  });

  it('retries on failure', async () => {
    mockFetch
      .mockRejectedValueOnce(new Error('Temporary failure'))
      .mockResolvedValueOnce({ data: 'success' });
    const result = await fetchDataWithRetry();
    expect(result.data).toBe('success');
  });
});
```
