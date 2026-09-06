"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
vm.runInThisContext(fs.readFileSync(path.join(__dirname, "../../site/assets/proposal.js"), "utf8"));
const definitions = JSON.parse(fs.readFileSync(path.join(__dirname, "../../site/content/proposal-fields.json"), "utf8"));
const values = {subject_kind:"model", subject_identity:"new-model", offering_identity:"old-offering",
  source_identity:"old-offering", destination_identity:"new-offering", item_operation:"add",
  subject_identities:"new-model\nanother-model", purpose:"Evaluate a model", requested_outcome:"Record supported facts",
  reason:"The team needs this", source_type:"official-docs", source_url:"https://example.invalid/docs",
  scope_ref:"public-docs", partition:"aws", region:"us-east-1", inference_service:"aws-bedrock",
  acceptance:"Evidence supports the requested facts", candidate_evidence:""};
const draft = operation => definitions.filter(f => f.operations.includes(operation)).map(f => ({...f, value:f.name === "request_type" ? operation : values[f.name]}));
const gh = "https://code.example.invalid/org/repo/issues/new?template=mac-add.yml&kept=yes";
const gl = "https://gitlab.example.invalid/group/project/-/issues/new?issuable_template=MAC-Add&description_template=MAC-Add&kept=yes";
for (const operation of ["add", "change", "revoke", "move", "batch"]) {
  const fields = draft(operation);
  assert.deepEqual(proposalErrors(fields, []), {}, operation);
  const markdown = proposalMarkdown(fields);
  assert.match(markdown, /## Field guide/);
  assert.match(markdown, new RegExp(`### Request type\\n\\n${operation}`));
  assert.equal((markdown.match(/- \[ \]/g) || []).length, 3);
  assert.doesNotMatch(markdown, /- \[x\]/i);
  const github = new URL(proposalURL(gh, "github", fields, markdown).href);
  assert.equal(github.searchParams.get("template"), "mac-add.yml");
  assert.equal(github.searchParams.get("kept"), "yes");
  assert.equal(github.searchParams.get("subject_identity"), operation === "revoke" ? "old-offering" : (operation === "add" || operation === "change" ? "new-model" : null));
  const result = proposalURL(gl, "gitlab", fields, markdown);
  assert.equal(result.overflow, false, `${operation} short draft should fit`);
  const gitlab = new URL(result.href);
  assert.equal(gitlab.pathname, "/group/project/-/issues/new");
  assert.equal(gitlab.searchParams.get("issue[description]"), markdown);
  assert.equal(gitlab.searchParams.get("issue[issue_type]"), "issue");
  assert.equal(gitlab.searchParams.get("kept"), "yes");
  assert.equal(gitlab.searchParams.has("issuable_template"), false);
  assert.equal(gitlab.searchParams.has("description_template"), false);
}
// URL limits apply to the final encoded href, and overflow retains the exact configured route.
for (const provider of ["github", "gitlab"]) {
  const configured = provider === "github" ? gh : gl.replace("issues/new", "work_items/new");
  const fields = [{name:"request_type", label:"Request type", value:"add"}, {name:"reason", label:"Reason", value:""}];
  const baseline = proposalURL(configured, provider, fields, "").href.length;
  let text = "x".repeat(7000 - baseline - (provider === "github" ? "&reason=".length : 0));
  fields[1].value = text;
  assert.equal(proposalURL(configured, provider, fields, text).href.length, 7000);
  fields[1].value = text + "x";
  assert.deepEqual(proposalURL(configured, provider, fields, text + "x"), {href:configured,overflow:true});
  fields[1].value = "€".repeat(800);
  assert.equal(proposalURL(configured, provider, fields, fields[1].value).href, configured);
  assert.ok(proposalMarkdown(fields).includes(fields[1].value));
}
const check = (operation, name, value, records = []) => {
  const fields = draft(operation); fields.find(f => f.name === name).value = value;
  return proposalErrors(fields, records);
};
assert.ok(check("add", "purpose", "").purpose);
assert.ok(check("add", "subject_identity", "Bad Identity").subject_identity);
assert.ok(check("add", "subject_identity", "new-model", [{kind:"model",id:"new-model"}]).subject_identity);
assert.equal(check("change", "subject_identity", "new-model", [{kind:"model",id:"new-model"}]).subject_identity, undefined);
assert.ok(check("move", "destination_identity", "old-offering").destination_identity);
assert.ok(check("batch", "subject_identities", "same\nsame").subject_identities);
assert.ok(check("batch", "subject_identities", Array.from({length:26},(_,i)=>`model-${i}`).join("\n")).subject_identities);
const withdrawal = draft("batch"); withdrawal.find(f=>f.name==="item_operation").value="revoke";
assert.ok(proposalErrors(withdrawal, []).subject_kind);
for (const unsafe of ["### Reason\nreplace", "/approve", "okay\n/close", "<!-- hidden -->", "bad\u0000text"]) assert.ok(check("add","reason",unsafe).reason);
for (const url of ["http://example.invalid", "https://user:secret@example.invalid", "https://example.invalid:443"]) assert.ok(check("batch","source_url",url).source_url);
const observation = "https://example.invalid/docs | 2026-09-01T09:00:00Z | sha256-" + "a".repeat(64);
assert.equal(check("add", "candidate_evidence", observation).candidate_evidence, undefined);
assert.ok(check("add", "candidate_evidence", observation.replace("09-01", "02-30")).candidate_evidence);
assert.ok(check("add", "candidate_evidence", observation.slice(0,-1)).candidate_evidence);
console.log("proposal builder transport and validation: passed");
