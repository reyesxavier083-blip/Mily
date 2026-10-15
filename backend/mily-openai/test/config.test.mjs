import test from "node:test";
import assert from "node:assert/strict";
import { assertProductionAuthConfig } from "../config.mjs";

test("production refuses to start without a bearer token", () => {
  assert.throws(
    () => assertProductionAuthConfig({ NODE_ENV: "production", MILY_API_TOKEN: "" }),
    /MILY_API_TOKEN must be configured/
  );
});

test("production refuses a whitespace-only bearer token", () => {
  assert.throws(
    () => assertProductionAuthConfig({ NODE_ENV: "production", MILY_API_TOKEN: "   " }),
    /MILY_API_TOKEN must be configured/
  );
});

test("production accepts a configured bearer token", () => {
  assert.doesNotThrow(() =>
    assertProductionAuthConfig({ NODE_ENV: "production", MILY_API_TOKEN: "test-token" })
  );
});

test("local development may omit the bearer token", () => {
  assert.doesNotThrow(() =>
    assertProductionAuthConfig({ NODE_ENV: "development", MILY_API_TOKEN: "" })
  );
});
