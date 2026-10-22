import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { ErrorAlert } from "./components";
import { ApiRequestError } from "./services/api";

describe("ErrorAlert", () => {
  it("shows a friendly quota message and readable profile stage", () => {
    const html = renderToStaticMarkup(<ErrorAlert error={new ApiRequestError(
      "http",
      "AI analysis is temporarily unavailable because the model quota has been reached. Please try again later.",
      503,
      "llm_quota_exceeded",
      "profile_analysis",
    )} />);

    expect(html).toContain("AI service temporarily unavailable");
    expect(html).toContain("during CV profile extraction");
    expect(html).not.toContain("profile_analysis");
  });

  it("shows a friendly message for an invalid model response", () => {
    const html = renderToStaticMarkup(<ErrorAlert error={new ApiRequestError(
      "http",
      "AI analysis could not process the model response. Please try again later.",
      502,
      "llm_invalid_response",
    )} />);

    expect(html).toContain("AI response could not be processed");
    expect(html).toContain("Please try again later.");
  });
});
