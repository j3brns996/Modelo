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
  assert.equal(github.searchParams.get("title"), proposalTitle(fields));
  for (const field of fields.filter(f=>f.type==="dropdown")) assert.equal(github.searchParams.get(field.name),field.value);
  assert.ok(markdown.startsWith("# " + proposalTitle(fields) + "\n"));
  assert.equal(github.searchParams.get("subject_identity"), operation === "revoke" ? "old-offering" : (operation === "add" || operation === "change" ? "new-model" : null));
  const result = proposalURL(gl, "gitlab", fields, markdown);
  assert.equal(result.overflow, false, `${operation} short draft should fit`);
  const gitlab = new URL(result.href);
  assert.equal(gitlab.pathname, "/group/project/-/issues/new");
  assert.equal(gitlab.searchParams.get("issue[description]"), markdown);
  assert.equal(gitlab.searchParams.get("issue[issue_type]"), "issue");
  assert.equal(gitlab.searchParams.get("issue[title]"), proposalTitle(fields));
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
// Exercise controller-only outcomes that depend on the browser environment.
(async () => {
  const controls = new Map();
  const listeners = new Map();
  const status = () => ({textContent:"",value:"",setAttribute(name,value){this[name]=value;}});
  const summary = {...status(), focus(){this.focused=true;}, select(){this.selected=true;}};
  const link = {...status(), addEventListener(name,fn){listeners.set("link:"+name,fn);}};
  const button = {addEventListener(name,fn){listeners.set("copy:"+name,fn);}};
  const urlStatus=status(), copyStatus=status(), validation=status();
  const groups = definitions.map(definition => {
    const input={value:definition.name==="request_type" ? "add" : values[definition.name],
      dataset:{field:definition.name,required:String(definition.required)},
      setAttribute(name,value){this[name]=value;}, focus(){this.focused=true;},matches(){return true;}};
    controls.set(definition.name,input);
    const error=status();
    return {dataset:{operations:definition.operations.join(" ")},querySelector(selector){
      return {"[data-field]":input,"label":{childNodes:[{textContent:definition.label}]},
        ".field-help":{textContent:definition.help},"[data-error]":error}[selector];
    }};
  });
  const form={dataset:{records:"[]",provider:"github"},hidden:true,
    querySelectorAll(selector){return selector==="[data-operations]" ? groups : [];},
    querySelector(selector){
      const name=selector.match(/^\[data-field="(.+)"\]$/);
      if(name) return controls.get(name[1]);
      return {"[data-proposal-summary]":summary,"[data-proposal-issue-link]":link,
        "[data-proposal-url-status]":urlStatus,"[data-proposal-copy-status]":copyStatus,
        "[data-proposal-validation]":validation,"[data-operation-help]":status(),
        "[data-copy-summary]":button}[selector];
    },getAttribute(){return gh;}, addEventListener(name,fn){listeners.set(name,fn);}};
  global.document={querySelectorAll(){return [form];},getElementById(){return null;}};
  global.window={location:new URL("https://example.invalid/propose/?operation=move")};
  Object.defineProperty(global,"navigator",{value:{clipboard:{}},configurable:true});
  initProposalBuilder();
  assert.equal(form.hidden,false);
  assert.equal(controls.get("request_type").value,"move");
  assert.equal(controls.get("subject_identity").disabled,true);
  assert.equal(controls.get("source_identity").disabled,false);
  controls.get("request_type").value="change";
  listeners.get("change")({target:controls.get("request_type")});
  assert.equal(controls.get("subject_identity").value,"new-model");
  assert.equal(controls.get("source_identity").disabled,true);
  assert.doesNotMatch(summary.value,/### Current offering identity/);
  let resolve;
  navigator.clipboard.writeText=()=>new Promise(done=>{resolve=done;});
  const pending=listeners.get("copy:click")();
  assert.equal(copyStatus.textContent,"");
  resolve(); await pending;
  assert.match(copyStatus.textContent,/Draft copied/);
  const previousURLStatus=urlStatus.textContent;
  for(const clipboard of [{writeText:async()=>{throw new Error("denied");}},undefined]) {
    navigator.clipboard=clipboard; summary.selected=false;
    await listeners.get("copy:click")();
    assert.equal(summary.selected,true);
    assert.equal(summary.focused,true);
    assert.equal(copyStatus.textContent,"Select and copy the draft manually.");
    assert.equal(urlStatus.textContent,previousURLStatus);
  }
  controls.get("subject_identity").value="Bad Identity";
  let prevented=false;
  listeners.get("link:click")({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);
  assert.equal(link["aria-disabled"],"true");
  assert.equal(controls.get("subject_identity").focused,true);
  console.log("proposal builder transport, validation and controller: passed");
})().catch(error=>{console.error(error);process.exitCode=1;});

(async () => {
  const request = modelRequest("", "Summarize customer documents", "Staff check summaries of support documents", "Bedrock pilot next quarter", {producer_domicile:["USA"],service_operator:["AWS"],processing_territory:["UK","EU"]});
  assert.deepEqual(request.errors, {});
  assert.equal(request.title, "Model request: Summarize customer documents");
  assert.doesNotMatch(request.markdown, /### (?:Request type|Modelo MAC request type)|subject_identity/);
  assert.ok(modelRequest("", "").errors.need);
  assert.match(request.markdown, /### Model rights owner domicile[\s\S]*?- \[x\] USA/);
  assert.equal(request.fields.find(field => field.name === "producer_domicile").value, "USA");
  assert.equal(request.fields.find(field => field.name === "processing_territory").value, "UK, EU");
  assert.equal(modelRequest("", "Need", "Use").fields.find(field => field.name === "processing_territory").value, "");
  assert.ok(modelRequest("", "Need", "Use", "", {producer_domicile:["unlisted"]}).errors.producer_domicile);
  assert.ok(modelRequest("", "Need a model").errors.intended_use);
  assert.ok(modelRequest("", "Need", "Use", "x".repeat(2049)).errors.deployment);
  assert.ok(modelRequest("/close", "Need a model").errors.model_reference);
  assert.ok(modelRequest("", "x".repeat(2049)).errors.need);
  for (const provider of ["github", "gitlab"]) {
    const configured = provider === "github" ? gh.replace("mac-add.yml", "model-request.yml") : gl;
    const url = new URL(proposalURL(configured, provider, request.fields, request.markdown, request.title).href);
    assert.equal(url.searchParams.get(provider === "github" ? "title" : "issue[title]"), request.title);
    assert.equal(url.searchParams.get(provider === "github" ? "need" : "issue[description]"), provider === "github" ? request.fields[1].value : request.markdown);
    if (provider === "github") for (const field of request.fields.filter(field => field.value)) assert.equal(url.searchParams.get(field.name), field.value);
    else for (const field of request.fields) assert.ok(url.searchParams.get("issue[description]").includes(`### ${field.label}`));
  }
  const nativeFetch = global.fetch;
  try {
    for (const [status, type, expected] of [[200, "basic", /not your login/], [403, "basic", /access denied/], [401, "basic", /401/], [404, "basic", /404/], [0, "opaqueredirect", /Could not verify/]]) {
      global.fetch = async (url, options) => {
        assert.equal(url, "https://gitlab.example.invalid/group/project");
        assert.equal(options.method, "GET");
        assert.equal(options.credentials, "include");
        assert.equal(options.redirect, "manual");
        assert.equal(options.cache, "no-store");
        return {status, type};
      };
      assert.match(await testRepositoryAccess("https://gitlab.example.invalid/group/project"), expected);
    }
    global.fetch = async () => {throw new TypeError("CORS, network or timeout");};
    assert.match(await testRepositoryAccess("https://gitlab.example.invalid/group/project"), /Could not verify/);
  } finally {global.fetch = nativeFetch;}
  console.log("simple request and GUI access status: passed");
})().catch(error => {console.error(error);process.exitCode = 1;});
