export const GITHUB_URL_REGEX = /^(?:https?:\/\/)?(?:www\.)?github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?\/?$/;

export const isValidGithubUrl = (url?: string): boolean => {
  if (!url || typeof url !== 'string') return false;
  return GITHUB_URL_REGEX.test(url.trim());
};

export const normalizeGithubUrl = (url: string): string => {
  const trimmed = url.trim();
  if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://')) {
    return `https://${trimmed}`;
  }
  return trimmed;
};
