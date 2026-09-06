"""Presentation-only guided proposal fields and published-record lookups."""

from html import escape
from datetime import timezone
from modelo.schemas import parse_rfc3339


OPERATIONS = {
    "add": "Add a new record", "change": "Update an existing record",
    "revoke": "Withdraw approved access", "move": "Replace an offering",
    "batch": "Make related changes together",
}


def lookup_records(catalogue):
    """Only the already validated publication projection may feed the picker."""
    records = []
    for kind, key in (("model", "models"), ("offering", "offerings"),
                      ("condition", "conditions"), ("evidence", "evidence")):
        for item in catalogue[key]:
            label = item.get("name", item.get("title", item["id"]))
            reference = item["id"]
            if kind == "condition":
                reference += "@" + str(item["version"])
                label += " (version " + str(item["version"]) + ")"
            if kind == "offering":
                label = item["id"] + " — " + item["model_id"] + " / " + item["inference_service_id"]
            record = {"kind": kind, "id": item["id"], "reference": reference, "label": label}
            if kind == "model":
                record["label"] += " — " + item["vendor_id"]
            if kind == "evidence":
                source = item["source"]
                uri = source.get("uri", source.get("documentation_uri", ""))
                record["label"] = uri + " — " + item["observed_at"]
                observed = parse_rfc3339(item["observed_at"]).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                record["observation"] = " | ".join((uri, observed, item["id"]))
            records.append(record)
    for kind, key in (("vendor", "vendors"), ("inference-service", "inference_services")):
        for identity, item in catalogue[key][key].items():
            records.append({"kind": kind, "id": identity, "reference": identity,
                            "label": item.get("name", identity)})
    return sorted(records, key=lambda item: (item["kind"], item["label"], item["reference"]))


def lookup_box(name, kind):
    return (
        f'<aside class="lookup-box" data-lookup="{name}" data-lookup-kind="{kind}">'
        f'<label for="lookup-{name}">Look up a record</label>'
        f'<input id="lookup-{name}" type="search" placeholder="Search name or exact ID" data-lookup-search>'
        f'<label for="matches-{name}" class="visually-hidden">Matching records for {name.replace("_", " ")}</label>'
        f'<select id="matches-{name}" size="3" data-lookup-results></select>'
        '<button type="button" class="button button--small" data-lookup-use>Use selected record</button>'
        '<small data-lookup-status></small></aside>'
    )


def render_fields(fields):
    controls = []
    lookup_kinds = {"subject_identity": "subject", "subject_identities": "subject",
                    "offering_identity": "offering", "source_identity": "offering",
                    "destination_identity": "offering", "inference_service": "inference-service",
                    "candidate_evidence": "evidence", "requested_outcome": "all"}
    for field in fields:
        name = field["name"]
        label = field["label"]
        identity = "proposal-" + name.replace("_", "-")
        attrs = f'id="{identity}" name="{name}" data-field="{name}" aria-describedby="help-{name} error-{name}"'
        required = ' data-required="true"' if field["required"] else ""
        if field["type"] == "dropdown":
            options = "".join('<option value="' + escape(value, quote=True) + '">'
                              + escape(OPERATIONS.get(value, value.replace("-", " ").title())) + '</option>'
                              for value in field["options"])
            control = f'<select {attrs}{required}>{options}</select>'
        else:
            length = 160 if name == "purpose" else (55000 if name in {"acceptance", "candidate_evidence"} else (6500 if name == "subject_identities" else 2048))
            attrs += f' maxlength="{length}" placeholder="{escape(field["placeholder"], quote=True)}"'
            control = (f'<textarea {attrs}{required} rows="3"></textarea>' if field["type"] == "textarea"
                       else f'<input type="text" {attrs}{required}>')
        lookup = lookup_box(name, lookup_kinds[name]) if name in lookup_kinds else ""
        controls.append(
            f'<div class="proposal-field" data-operations="{" ".join(field["operations"])}" data-name="{name}">'
            f'<div><label for="{identity}">{escape(label)}'
            + (' <span class="optional">(optional)</span>' if not field["required"] else '')
            + f'</label><p id="help-{name}" class="field-help">{escape(field["help"])}</p>'
            + control + f'<p id="error-{name}" class="field-error" data-error="{name}"></p></div>'
            + lookup + '</div>'
        )
    return "\n".join(controls)


def render_gitlab_template(operation, fields, lookup_url):
    """Guidance lives before the machine-recognised answer headings."""
    relevant = [field for field in fields if operation in field["operations"]]
    text = f'# {OPERATIONS[operation]}\n\nComplete the answers below, then review and submit this issue. This request is not approval.\n\n'
    text += f'[Look up model IDs, offerings, services, conditions and evidence]({lookup_url})\n\n'
    text += '## Field guide\n\n'
    for field in relevant:
        text += f'**{field["label"]}:** {field["help"]}\n\n'
        if field["name"] in {"subject_identity", "subject_identities", "offering_identity", "source_identity", "destination_identity", "requested_outcome", "candidate_evidence", "inference_service"}:
            text += f'[Look up records]({lookup_url.split("#")[0]}?operation={operation}#lookup-{field["name"]})\n\n'
        if field.get("options") and field["name"] != "request_type":
            text += 'Choose: ' + ', '.join('`' + value + '`' for value in field['options']) + '.\n\n'
    text += '## Your answers\n\n'
    for field in relevant:
        value = operation if field["name"] == "request_type" else '_No response_'
        text += f'### {field["label"]}\n\n{value}\n\n'
    return text + '### Before submitting\n\n- [ ] I checked for existing records and requests.\n- [ ] I have not included credentials, tokens or private commercial terms.\n- [ ] I understand that this request is not approval.\n'
