import { describe, it, expect } from 'vitest';
import { isValidGithubUrl } from '../src/utils/github';

describe('isValidGithubUrl', () => {
  it('validates standard public GitHub repository URLs', () => {
    expect(isValidGithubUrl('https://github.com/fastapi/fastapi')).toBe(true);
    expect(isValidGithubUrl('https://www.github.com/pallets/flask')).toBe(true);
    expect(isValidGithubUrl('https://github.com/django/django/')).toBe(true);
    expect(isValidGithubUrl('https://github.com/owner/repo-name.git')).toBe(true);
    expect(isValidGithubUrl('http://github.com/user/my_repo_123')).toBe(true);
  });

  it('rejects invalid or non-GitHub repository URLs', () => {
    expect(isValidGithubUrl('')).toBe(false);
    expect(isValidGithubUrl('   ')).toBe(false);
    expect(isValidGithubUrl('https://gitlab.com/owner/repo')).toBe(false);
    expect(isValidGithubUrl('https://github.com/')).toBe(false);
    expect(isValidGithubUrl('https://github.com/onlyowner')).toBe(false);
    expect(isValidGithubUrl('not-a-url')).toBe(false);
    expect(isValidGithubUrl(undefined)).toBe(false);
  });
});
