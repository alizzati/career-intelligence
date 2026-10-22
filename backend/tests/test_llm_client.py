from types import SimpleNamespace
from unittest import mock

import pytest

from app.agents.llm_client import GeminiClient
from app.agents.llm_errors import LLMInvalidResponseError, LLMQuotaExceededError


def _client(response=None, error=None):
    sdk = mock.Mock()
    if error is not None:
        sdk.models.generate_content.side_effect = error
    else:
        sdk.models.generate_content.return_value = SimpleNamespace(text=response)
    with mock.patch("app.agents.llm_client.genai.Client", return_value=sdk):
        client = GeminiClient(api_key="synthetic-test-key")
    return client, sdk


def test_complete_json_returns_a_json_object_without_exposing_credentials():
    client, sdk = _client('{"skills": []}')

    assert client.complete_json("system", "synthetic CV", max_tokens=8192) == {"skills": []}
    kwargs = sdk.models.generate_content.call_args.kwargs
    assert kwargs["config"].max_output_tokens == 8192
    assert "synthetic-test-key" not in repr(sdk.models.generate_content.call_args)


@pytest.mark.parametrize("response", ["", "not-json", "[]"])
def test_complete_json_classifies_unusable_model_responses(response):
    client, _ = _client(response)

    with pytest.raises(LLMInvalidResponseError):
        client.complete_json("system", "synthetic CV")


def test_complete_json_converts_provider_429_to_safe_quota_error():
    class ProviderError(Exception):
        code = 429

    client, _ = _client(error=ProviderError("private provider details"))

    with pytest.raises(LLMQuotaExceededError) as exc:
        client.complete_json("system", "synthetic CV")

    assert "private provider details" not in str(exc.value)
