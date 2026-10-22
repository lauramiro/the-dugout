import logging


def test_azure_sdk_request_logging_is_off_in_the_runner_and_the_service():
    # A dependency turns the root logger to INFO; the Azure SDK's per-request lines must not follow.
    import dugout.service.app  # noqa: F401
    import dugout.stream.pipeline  # noqa: F401

    http = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
    assert http.getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("azure.eventhub").getEffectiveLevel() >= logging.WARNING
