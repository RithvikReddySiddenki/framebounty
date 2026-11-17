import json

import httpx
import pytest

from framebounty.verification import GeminiFrames, ProviderFailure, fixture_assessment, parse_assessment


def output():
    return fixture_assessment().model_dump()


def test_quality_checks_cannot_replace_task_completion():
    data = output()
    data["visibility"]["result"] = "pass"
    data["task_completion"]["result"] = "fail"
    assessment = parse_assessment(json.dumps(data), 15000)
    assert assessment.task_completion.result == "fail"
    assert not hasattr(assessment, "approved")


def test_model_cannot_inject_payment_tools_or_fabricated_timestamps():
    data = output()
    data["approve_payment"] = True
    with pytest.raises(ProviderFailure):
        parse_assessment(json.dumps(data), 15000)
    data = output()
    data["task_completion"]["timestamps_ms"] = [30001]
    with pytest.raises(ProviderFailure):
        parse_assessment(json.dumps(data), 15000)


@pytest.mark.parametrize("status,body", [(429, {}), (500, {}), (200, {"candidates": []}), (200, {"candidates": [{"finishReason": "MAX_TOKENS"}]})])
def test_provider_errors_fail_visibly(status, body):
    adapter = GeminiFrames("test-only", "account-verified-model", httpx.MockTransport(lambda _: httpx.Response(status, json=body)))
    with pytest.raises(ProviderFailure):
        adapter.assess([(0, b"\xff\xd8\xfftest")], "Complete the fold", 15000)


def test_provider_timeout_and_missing_configuration():
    with pytest.raises(ProviderFailure):
        GeminiFrames("", "")
    def timeout(request):
        raise httpx.ReadTimeout("test outage", request=request)
    adapter = GeminiFrames("test-only", "account-verified-model", httpx.MockTransport(timeout))
    with pytest.raises(ProviderFailure):
        adapter.assess([(0, b"\xff\xd8\xfftest")], "Complete the fold", 15000)


def test_validated_observation_is_still_only_an_observation():
    def response(request):
        assert request.headers["x-goog-api-key"] == "test-only"
        body = json.loads(request.content)
        assert "systemInstruction" in body
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(output())}]}}]})
    adapter = GeminiFrames("test-only", "account-verified-model", httpx.MockTransport(response))
    assert adapter.assess([(0, b"\xff\xd8\xfftest")], "Complete the fold", 15000).task_completion.result == "uncertain"
