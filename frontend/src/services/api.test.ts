import { afterEach, describe, expect, it, vi } from "vitest";
import { analyzeCv, analyzeProfile, createUser, ApiRequestError } from "./api";

const reply = (status: number, body: unknown) =>
  vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
afterEach(() => vi.unstubAllGlobals());

describe("api client (contract tests with mocked fetch; not end-to-end)", () => {
  it("network failure -> kind=network", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    await expect(analyzeProfile(1)).rejects.toMatchObject({ kind: "network" });
  });
  it("HTTP error body is parsed into code/message/stage", async () => {
    vi.stubGlobal("fetch", reply(404, { error: { code: "user_not_found", message: "no user" } }));
    const err = await analyzeProfile(9).catch(e => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect(err).toMatchObject({ kind: "http", status: 404, code: "user_not_found", message: "no user" });
  });
  it("quota errors preserve the actionable backend message", async () => {
    vi.stubGlobal("fetch", reply(503, { error: {
      code: "llm_quota_exceeded",
      message: "AI analysis is temporarily unavailable because the model quota has been reached. Please try again later.",
      stage: "profile_analysis",
    } }));
    const err = await analyzeCv(5, new File(["synthetic"], "cv.txt")).catch(e => e);
    expect(err).toMatchObject({
      kind: "http", status: 503, code: "llm_quota_exceeded",
      stage: "profile_analysis",
      message: "AI analysis is temporarily unavailable because the model quota has been reached. Please try again later.",
    });
  });
  it("non-JSON error body still yields an http error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => { throw new Error("x"); } }));
    await expect(analyzeProfile(1)).rejects.toMatchObject({ kind: "http", status: 502 });
  });
  it("HTTP 200 with verified=false resolves (not thrown) and keeps final_status", async () => {
    vi.stubGlobal("fetch", reply(200, { final_status: "VERIFICATION_FAILED", verified: false }));
    await expect(analyzeProfile(1)).resolves.toMatchObject({ final_status: "VERIFICATION_FAILED", verified: false });
  });
  it("profile request sends JSON and omits empty target", async () => {
    const f = reply(200, {}); vi.stubGlobal("fetch", f);
    await analyzeProfile(5, "");
    const [url, init] = f.mock.calls[0];
    expect(url).toBe("/api/analysis/profile");
    expect(JSON.parse(init.body)).toEqual({ user_id: 5 });
  });
  it("CV upload sends multipart form fields", async () => {
    const f = reply(200, {}); vi.stubGlobal("fetch", f);
    await analyzeCv(5, new File(["x"], "cv.txt"), "C01");
    const form = f.mock.calls[0][1].body as FormData;
    expect(form.get("user_id")).toBe("5"); expect(form.get("target_career_id")).toBe("C01"); expect(form.get("file")).toBeInstanceOf(File);
  });
  it("createUser posts email and full_name", async () => {
    const f = reply(200, { user_id: 3 }); vi.stubGlobal("fetch", f);
    await expect(createUser("a@b.test", "A B")).resolves.toEqual({ user_id: 3 });
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ email: "a@b.test", full_name: "A B" });
  });
});
