import {
  Decoration,
  EditorView,
  ViewPlugin,
  WidgetType,
  type DecorationSet,
  type ViewUpdate,
} from '@codemirror/view';

/** Display real line boundaries without inserting anything into the document. */
export function newlineMarkers(title: string) {
  class BreakMarker extends WidgetType {
    toDOM(view: EditorView) {
      const marker = view.dom.ownerDocument.createElement('span');
      marker.className = 'cm-hard-break';
      marker.textContent = '↵';
      marker.title = title;
      marker.setAttribute('aria-hidden', 'true');
      return marker;
    }
    ignoreEvent() {
      return true;
    }
  }
  const mark = Decoration.widget({ widget: new BreakMarker(), side: 1 });
  const build = (view: EditorView) => {
    const positions = new Set<number>();
    for (const range of view.visibleRanges) {
      for (
        let n = view.state.doc.lineAt(range.from).number;
        n < view.state.doc.lines;
        n++
      ) {
        const line = view.state.doc.line(n);
        if (line.from > range.to) break;
        positions.add(line.to);
      }
    }
    return Decoration.set(
      [...positions].sort((a, b) => a - b).map((p) => mark.range(p)),
    );
  };
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet;
      constructor(view: EditorView) {
        this.decorations = build(view);
      }
      update(update: ViewUpdate) {
        if (update.docChanged || update.viewportChanged)
          this.decorations = build(update.view);
      }
    },
    { decorations: (value) => value.decorations },
  );
}
