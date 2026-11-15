import { test } from "node:test";
import assert from "node:assert/strict";

import {
  MAX_UPLOAD_ATTEMPTS,
  uploadWithRetry,
  type UploadRetryOptions,
} from "../src/lib/upload-retry.ts";

const UPLOAD_URL = "https://api.retailmind.example/api/upload/direct";
const TRANSPORT_ERROR =
  "The direct upload connection was interrupted before the server replied. Check your connection and retry.";
const TICKET_ERROR = "The upload service could not be reached. Check your connection and retry.";

function ticket(token: string) {
  return { token, upload_url: UPLOAD_URL };
}

/**
 * Build options that record every observable step, so the test can assert the
 * exact ordering of progress reset, ticket minting, and upload attempts.
 */
function recorder(overrides: Partial<UploadRetryOptions<string>> = {}) {
  const events: string[] = [];
  let minted = 0;

  const options: UploadRetryOptions<string> = {
    requestTicket: async () => {
      minted += 1;
      events.push(`ticket:${minted}`);
      return ticket(`ticket-${minted}`);
    },
    uploadOnce: async (current) => {
      events.push(`upload:${current.token}`);
      return "stored";
    },
    onAttemptStart: () => events.push("progress:0"),
    onRetry: () => events.push("retry-message"),
    wait: async () => {},
    ...overrides,
  };

  return { events, options, minted: () => minted };
}

test("resets progress before the retry attempt", async () => {
  const { events, options } = recorder();
  options.uploadOnce = async (current) => {
    events.push(`upload:${current.token}`);
    if (current.token === "ticket-1") throw new Error(TRANSPORT_ERROR);
    return "stored";
  };

  assert.equal(await uploadWithRetry(options), "stored");
  assert.deepEqual(events, [
    "progress:0",
    "ticket:1",
    "upload:ticket-1",
    "retry-message",
    "progress:0",
    "ticket:2",
    "upload:ticket-2",
  ]);
});

test("mints a fresh single-use ticket for every attempt", async () => {
  const tokens: string[] = [];
  const { options } = recorder();
  options.uploadOnce = async (current) => {
    tokens.push(current.token);
    if (tokens.length === 1) throw new Error(TRANSPORT_ERROR);
    return "stored";
  };

  await uploadWithRetry(options);
  assert.deepEqual(tokens, ["ticket-1", "ticket-2"]);
});

test("keeps the two-attempt policy for repeated transport failures", async () => {
  const { events, options, minted } = recorder();
  options.uploadOnce = async (current) => {
    events.push(`upload:${current.token}`);
    throw new Error(TRANSPORT_ERROR);
  };

  await assert.rejects(uploadWithRetry(options), { message: TRANSPORT_ERROR });

  assert.equal(minted(), MAX_UPLOAD_ATTEMPTS);
  assert.equal(events.filter((event) => event === "progress:0").length, MAX_UPLOAD_ATTEMPTS);
  assert.equal(events.filter((event) => event.startsWith("upload:")).length, MAX_UPLOAD_ATTEMPTS);
});

test("does not retry server validation failures", async () => {
  const failures = [
    "Your session or upload ticket expired before the upload finished. Sign in again, then retry — the file was not stored.",
    "The upload is larger than the server accepts. Split the workbook or reduce the row count, then retry. The original file was not stored.",
    "That file type is not supported. Use a CSV or Excel workbook (.csv, .xlsx, .xls, .xlsm).",
    "The file could not be parsed. Check the column headers, remove merged cells, and retry.",
  ];

  for (const failure of failures) {
    const { events, options, minted } = recorder();
    options.uploadOnce = async (current) => {
      events.push(`upload:${current.token}`);
      throw new Error(failure);
    };

    await assert.rejects(uploadWithRetry(options), { message: failure });

    assert.equal(minted(), 1);
    assert.deepEqual(events, ["progress:0", "ticket:1", "upload:ticket-1"]);
  }
});

test("retries a transport-level ticket failure without the upload retry banner", async () => {
  let calls = 0;
  const events: string[] = [];

  const result = await uploadWithRetry<string>({
    requestTicket: async () => {
      calls += 1;
      events.push(`ticket:${calls}`);
      if (calls === 1) throw new Error(TICKET_ERROR);
      return ticket(`ticket-${calls}`);
    },
    uploadOnce: async (current) => {
      events.push(`upload:${current.token}`);
      return "stored";
    },
    onAttemptStart: () => events.push("progress:0"),
    onRetry: () => events.push("retry-message"),
    wait: async () => {},
  });

  assert.equal(result, "stored");
  assert.deepEqual(events, [
    "progress:0",
    "ticket:1",
    "progress:0",
    "ticket:2",
    "upload:ticket-2",
  ]);
});
