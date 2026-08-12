from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.repo_validation import validate_github_repository
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_validate_github_repository_allowed_mit():
    repo_response = MagicMock()
    repo_response.status_code = 200
    repo_response.json.return_value = {"private": False}

    lic_response = MagicMock()
    lic_response.status_code = 200
    lic_response.json.return_value = {"license": {"spdx_id": "MIT"}}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [repo_response, lic_response]
        spdx_id = await validate_github_repository("fastapi", "fastapi")
        assert spdx_id == "MIT"


@pytest.mark.asyncio
async def test_validate_github_repository_repo_not_found_404():
    repo_response = MagicMock()
    repo_response.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = repo_response
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "nonexistent-repo")
        assert exc_info.value.status_code == 404
        detail = cast(dict[str, Any], exc_info.value.detail)
        assert detail["message"] == "Repository does not exist or is private."
        assert "check the URL for typos" in detail["reason"]


@pytest.mark.asyncio
async def test_validate_github_repository_private_repo():
    repo_response = MagicMock()
    repo_response.status_code = 200
    repo_response.json.return_value = {"private": True}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = repo_response
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "private-repo")
        assert exc_info.value.status_code == 403
        detail = cast(dict[str, Any], exc_info.value.detail)
        assert detail["message"] == "Private repositories are not supported."


@pytest.mark.asyncio
async def test_validate_github_repository_no_license_404():
    repo_response = MagicMock()
    repo_response.status_code = 200
    repo_response.json.return_value = {"private": False}

    lic_response = MagicMock()
    lic_response.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [repo_response, lic_response]
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "no-license-repo")
        assert exc_info.value.status_code == 403
        detail = cast(dict[str, Any], exc_info.value.detail)
        assert detail["message"] == "Repository has no license (All Rights Reserved). Cannot index."


@pytest.mark.asyncio
async def test_validate_github_repository_noassertion():
    repo_response = MagicMock()
    repo_response.status_code = 200
    repo_response.json.return_value = {"private": False}

    lic_response = MagicMock()
    lic_response.status_code = 200
    lic_response.json.return_value = {"license": {"spdx_id": "NOASSERTION"}}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [repo_response, lic_response]
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "custom-repo")
        assert exc_info.value.status_code == 403
        detail = cast(dict[str, Any], exc_info.value.detail)
        assert detail["message"] == "Repository uses an unrecognized or custom license."


@pytest.mark.asyncio
async def test_validate_github_repository_unsupported_license():
    repo_response = MagicMock()
    repo_response.status_code = 200
    repo_response.json.return_value = {"private": False}

    lic_response = MagicMock()
    lic_response.status_code = 200
    lic_response.json.return_value = {"license": {"spdx_id": "PolyForm-Noncommercial-1.0.0"}}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [repo_response, lic_response]
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "polyform-repo")
        assert exc_info.value.status_code == 403
        detail = cast(dict[str, Any], exc_info.value.detail)
        assert "not supported" in detail["message"]


@pytest.mark.asyncio
async def test_validate_github_repository_http_error():
    repo_response = MagicMock()
    repo_response.status_code = 500

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = repo_response
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "broken-repo")
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_github_repository_request_exception():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.RequestError("Network error")
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "network-error-repo")
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_github_repository_exceeds_max_repo_size():
    repo_response = MagicMock()
    repo_response.status_code = 200
    repo_response.json.return_value = {"private": False, "size": 600000}  # 600 MB (exceeds 500 MB limit)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = repo_response
        with pytest.raises(HTTPException) as exc_info:
            await validate_github_repository("owner", "large-repo")
        assert exc_info.value.status_code == 413
        detail = cast(dict[str, Any], exc_info.value.detail)
        assert "exceeds maximum allowed limit" in detail["message"]


@pytest.mark.asyncio
async def test_validate_github_repository_within_max_repo_size():
    repo_response = MagicMock()
    repo_response.status_code = 200
    repo_response.json.return_value = {"private": False, "size": 100000}  # 100 MB

    lic_response = MagicMock()
    lic_response.status_code = 200
    lic_response.json.return_value = {"license": {"spdx_id": "MIT"}}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [repo_response, lic_response]
        spdx_id = await validate_github_repository("owner", "normal-repo")
        assert spdx_id == "MIT"
