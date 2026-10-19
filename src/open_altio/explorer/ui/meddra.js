/* A MedDRA term FDA wrote (a reaction, an indication, the reaction that came back when the drug was
   given again), shown with what the release reads it to: MedDRA's spelling of an old term written in
   capitals, with FDA's capitals under it (rule legacy-term-spelling), and, for a viewer with
   MedDRA's licensed part, the current PT under FDA's text, with the MedDRA version and its rule
   (rule meddra-terms). Nobody else is shown which PT a text reads to. */

import { esc, ruleTag, tip } from './util.js';

// how FDA's text reached its current PT (/api/case's matched_as)
const HOW = {
  pt: "FDA's text is this PT, written another way",
  llt: "FDA's text is a lower level term of this PT",
  former_name: "FDA's text is a name MedDRA used before for this PT",
};

// the current PT a text reads to: a quiet mark beside it on the case list and under it in a case, its
// MedDRA version in the tip
export function ptMark(current, version) {
  if (!current) return '';
  return ` <span class="oa-pt" ${tip(`${HOW[current.matched_as] || ''}, in MedDRA ${version}`)}>PT: ${esc(current.name)}</span>`;
}

// in a case: the term as shown (and `after` it, such as the drug an indication is for), FDA's own
// text under it where MedDRA's spelling differs, and the current PT where this viewer may see it
export function termShown(shown, fda, current = null, version = '', after = '') {
  const text = shown || fda || '';
  const spelled = fda && text !== fda
    ? ` <span class="oa-fda" ${tip('As FDA published it')}>FDA: ${esc(fda)}</span><span class="oa-case-note">${ruleTag('legacy-term-spelling', 'fixed rule: legacy-term-spelling')}</span>`
    : '';
  return `${esc(text)}${after}${spelled}${ptMark(current, version)}`;
}

// on the case list, above the table: what the PT beside FDA's text is, and from which version
export const ptNote = (version) => (version
  ? `<p class="oa-pt-note">Reactions as FDA wrote them, each with its current PT in MedDRA ${esc(version)} where that is another term.</p>`
  : '');
