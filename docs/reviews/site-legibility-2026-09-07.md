# Site and README legibility review

Issue: [#97](https://github.com/j3brns996/Modelo/issues/97)

## Findings

An independent read-only review found two high-impact defects:

- `site/assets/site.css` truncated change-history paragraphs and list items with
  line clamping, `nowrap`, and ellipses. Users could see the full value only in
  a `title` attribute.
- Paragraphs used the 70-character reading measure, while lists and definition
  lists could expand to the 76-rem page container. The resulting columns did not
  align.

The review also found dense README paragraphs and two audiences mixed on the
proposal page. The overview already provides a useful 5W+How pattern.

## Correction plan

1. Remove visual truncation and allow history text to wrap.
2. Apply the shared reading measure to prose lists and definition lists. Keep
   data tables wide, with fixed columns and wrapped cell content.
3. Rewrite README status, action, and workflow explanations with direct subjects,
   short sentences, sentence case, and the 5W+How questions: who acts, what is
   recorded, why approval is bounded, when and where facts apply, and how CI and
   branch controls finish the change.
4. Preserve the authoring rules, native Git provider form flow, synthetic status,
   undecided licence, and separation between offering review and system NFRs.

## Verification

- Source regression checks assert wrapped history rules, fixed table layout, and
  aligned prose measures.
- Run the site tests first, then the configured local CI checks.
- Review the rendered site at 320, 580, 880, and desktop widths. Confirm that
  history paths remain readable, prose columns align, and tables wrap without
  hiding content.
