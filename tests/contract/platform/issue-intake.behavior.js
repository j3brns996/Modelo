"use strict";

const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const root = path.resolve(__dirname, "../../..");
const workflow = fs.readFileSync(
  path.join(root, ".github/workflows/issue-intake.yml"),
  "utf8",
);
const scriptMarker = "          script: |\n";
const markerOffset = workflow.indexOf(scriptMarker);
assert.notStrictEqual(markerOffset, -1, "inline github-script must exist");
const script = workflow
  .slice(markerOffset + scriptMarker.length)
  .split("\n")
  .map((line) => line.startsWith("            ") ? line.slice(12) : line)
  .join("\n");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const execute = new AsyncFunction("context", "github", "process", "require", script);

const eventBody = [
  "### Request type",
  "",
  "add",
  "",
  "<!-- modelo:intake-generated-start -->",
].join("\n");
const compiledBody = "### Invalid legacy proposal\n\nRestore the missing fields.\n";
const commentBody = "<!-- modelo:intake-result -->\nProposal needs attention.\n";
for (const trigger of [
  "### Modelo MAC request type",
  "<!-- modelo:intake-generated-start -->",
  "<!-- modelo:intake-generated-end -->",
]) {
  assert.ok(!compiledBody.includes(trigger), `compiled body unexpectedly retained ${trigger}`);
}

async function runScenario({ currentBody, retainUpdate = true, writes = [] }) {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), "modelo-intake-behavior-"));
  const issueOutput = path.join(temporary, "issue.md");
  const commentOutput = path.join(temporary, "comment.md");
  fs.writeFileSync(issueOutput, compiledBody, "utf8");
  fs.writeFileSync(commentOutput, commentBody, "utf8");
  let storedBody = currentBody;
  const context = {
    repo: { owner: "example", repo: "modelo" },
    issue: { number: 43 },
    payload: { issue: { body: eventBody } },
  };
  const github = {
    rest: {
      issues: {
        listComments: async () => ({ data: [] }),
        get: async () => ({ data: { body: storedBody } }),
        update: async ({ body }) => {
          writes.push({ type: "update", body });
          if (retainUpdate) storedBody = body;
        },
        updateComment: async (request) => {
          writes.push({ type: "updateComment", request });
        },
        createComment: async ({ body }) => {
          writes.push({ type: "createComment", body });
        },
      },
    },
  };
  const environment = {
    ...process,
    env: {
      ...process.env,
      ISSUE_BODY_OUTPUT: issueOutput,
      COMMENT_OUTPUT: commentOutput,
    },
  };
  try {
    await execute(context, github, environment, require);
    return { writes, storedBody };
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

(async () => {
  const completed = await runScenario({ currentBody: eventBody });
  assert.deepStrictEqual(
    completed.writes.map(({ type }) => type),
    ["update", "createComment"],
    "body and comment writes must complete in one run even after all triggers disappear",
  );
  assert.strictEqual(completed.storedBody, compiledBody);
  assert.strictEqual(completed.writes[1].body, commentBody);

  const staleWrites = [];
  await assert.rejects(
    runScenario({ currentBody: "a newer issue body", writes: staleWrites }),
    /refusing stale writes/,
  );
  assert.deepStrictEqual(staleWrites, [], "stale events must perform no writes");

  const mismatchWrites = [];
  await assert.rejects(
    runScenario({
      currentBody: eventBody,
      retainUpdate: false,
      writes: mismatchWrites,
    }),
    /compiled issue body was not retained/,
  );
  assert.deepStrictEqual(
    mismatchWrites.map(({ type }) => type),
    ["update"],
    "post-update mismatch must block every comment write",
  );

  process.stdout.write("issue intake workflow behavior: ok\n");
})().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
