import { StateField, type EditorState } from '@codemirror/state';
import { Decoration, EditorView, type DecorationSet } from '@codemirror/view';

import { configSectionStarts } from '@/utils/configParser';

function sections(state: EditorState): DecorationSet {
  return Decoration.set(
    configSectionStarts(state.doc.toString())
      .filter((from) => from > 0)
      .map((from) =>
        Decoration.line({ class: 'cm-config-section' }).range(from),
      ),
  );
}

/** Presentation only: document text, selection and clipboard stay intact. */
export const configSectionSpacing = StateField.define<DecorationSet>({
  create: sections,
  update: (value, transaction) =>
    transaction.docChanged ? sections(transaction.state) : value,
  provide: (field) => EditorView.decorations.from(field),
});
