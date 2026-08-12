import httpx
from fastapi import HTTPException, status

from app.config import settings

# A comprehensive allowlist of permissive, non-copyleft SPDX identifiers.
ALLOWED_SPDX_IDS: frozenset[str] = frozenset(
    {
        # --- Most Common ---
        "MIT",
        "Apache-2.0",
        "BSD-3-Clause",
        # --- Other BSD Variants ---
        "BSD-2-Clause",
        "BSD-1-Clause",
        "BSD-4-Clause",  # Original BSD (includes advertising clause, but still permissive)
        "0BSD",  # Zero-Clause BSD
        # --- Public Domain / No Attribution Required ---
        "Unlicense",
        "WTFPL",
        "CC0-1.0",  # Creative Commons Zero v1.0 Universal
        "MIT-0",  # MIT No Attribution
        # --- Other Standard Permissive Licenses ---
        "ISC",
        "Zlib",
        "BSL-1.0",  # Boost Software License (Note: NOT the Business Source License)
        "PostgreSQL",
        "NCSA",  # University of Illinois/NCSA Open Source License
        # --- Modern & Corporate Permissive ---
        "UPL-1.0",  # Universal Permissive License (Oracle)
        "BlueOak-1.0.0",  # Blue Oak Model License (Highly regarded modern permissive license)
        "MulanPSL-2.0",  # Mulan Permissive Software License v2
    }
)


async def validate_github_repository(owner: str, repo: str) -> str:
    """Checks repository existence, privacy status, size limit, and license via GitHub REST API."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "repotraverse-backend",
    }
    if settings.github_pat and settings.github_pat.get_secret_value():
        headers["Authorization"] = f"Bearer {settings.github_pat.get_secret_value()}"

    repo_url = f"https://api.github.com/repos/{owner}/{repo}"
    license_url = f"https://api.github.com/repos/{owner}/{repo}/license"

    async with httpx.AsyncClient() as client:
        # Check repository existence and privacy
        try:
            repo_res = await client.get(repo_url, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Failed to connect to GitHub API.",
                    "reason": "Unable to verify repository details from GitHub. Please try again later.",
                },
            ) from exc

        if repo_res.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "Repository does not exist or is private.",
                    "reason": "Please check the URL for typos or ensure the repository is publicly accessible on GitHub.",
                },
            )

        if repo_res.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Failed to fetch repository information from GitHub.",
                    "reason": "GitHub API returned an unexpected response. Please try again later.",
                },
            )

        repo_data = repo_res.json()
        if repo_data.get("private") is True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Private repositories are not supported.",
                    "reason": "This tool only supports public GitHub repositories for indexing.",
                },
            )

        # Check repository size limit (GitHub API returns size in KB)
        size_kb = repo_data.get("size")
        max_repo_size_mb = settings.max_repo_size_mb
        if isinstance(size_kb, (int, float)) and size_kb > max_repo_size_mb * 1024:
            size_mb = size_kb / 1024
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "message": f"Repository size ({size_mb:.1f} MB) exceeds maximum allowed limit ({max_repo_size_mb} MB).",
                    "reason": f"To ensure system performance and storage limits, repositories larger than {max_repo_size_mb} MB cannot be indexed.",
                },
            )

        # Check repository license
        try:
            lic_res = await client.get(license_url, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Failed to connect to GitHub API.",
                    "reason": "Unable to verify repository license details. Please try again later.",
                },
            ) from exc

        if lic_res.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Repository has no license (All Rights Reserved). Cannot index.",
                    "reason": "We only support indexing repositories with open source licenses to avoid copyright restrictions.",
                },
            )

        if lic_res.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Failed to fetch repository license information from GitHub.",
                    "reason": "GitHub API returned an unexpected response while checking license details.",
                },
            )

        data = lic_res.json()
        spdx_id = data.get("license", {}).get("spdx_id")

        if not spdx_id or spdx_id == "NOASSERTION":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Repository uses an unrecognized or custom license.",
                    "reason": "Only standard open source licenses recognized by SPDX can be verified for automated processing.",
                },
            )

        if spdx_id not in ALLOWED_SPDX_IDS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": f"License '{spdx_id}' is not supported by this tool.",
                    "reason": f"The '{spdx_id}' license is excluded to comply with open source policy requirements.",
                },
            )

        return spdx_id
