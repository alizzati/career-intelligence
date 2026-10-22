"""Safe, typed failures from the configured LLM client."""


class LLMQuotaExceededError(RuntimeError):
    """The provider rejected a request because its quota is exhausted."""

    def __init__(self):
        super().__init__("The configured model quota is exhausted.")


class LLMInvalidResponseError(RuntimeError):
    """The provider response was empty, invalid JSON, or not a JSON object."""

    def __init__(self):
        super().__init__("The configured model returned an unusable JSON response.")
