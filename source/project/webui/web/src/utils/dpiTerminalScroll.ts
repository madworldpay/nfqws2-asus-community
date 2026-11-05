import type { Terminal } from '@xterm/xterm';

// xterm 6 handles wheel events itself, but not vertical touch gestures.
// Keep horizontal pans native so wide original tables remain reachable.
export const bindDpiTerminalScrolling = (
  terminal: Pick<
    Terminal,
    | 'rows'
    | 'element'
    | 'scrollLines'
    | 'scrollPages'
    | 'scrollToTop'
    | 'scrollToBottom'
    | 'attachCustomKeyEventHandler'
  >,
  host: HTMLElement,
) => {
  let gesture: {
    x: number;
    y: number;
    lastY: number;
    remainder: number;
    axis: 'pending' | 'horizontal' | 'vertical';
  } | null = null;
  const reset = () => {
    gesture = null;
  };
  const start = (event: TouchEvent) => {
    if (event.touches.length !== 1) return reset();
    const touch = event.touches[0];
    gesture = {
      x: touch.clientX,
      y: touch.clientY,
      lastY: touch.clientY,
      remainder: 0,
      axis: 'pending',
    };
  };
  const move = (event: TouchEvent) => {
    if (!gesture || event.touches.length !== 1) return reset();
    const touch = event.touches[0];
    if (gesture.axis === 'pending') {
      const dx = Math.abs(touch.clientX - gesture.x);
      const dy = Math.abs(touch.clientY - gesture.y);
      if (Math.max(dx, dy) < 6) return;
      gesture.axis = dy > dx ? 'vertical' : 'horizontal';
    }
    if (gesture.axis !== 'vertical') return;
    event.preventDefault();
    const height = terminal.element
      ?.querySelector('.xterm-screen')
      ?.getBoundingClientRect().height;
    const rowHeight = height && terminal.rows ? height / terminal.rows : 14;
    gesture.remainder += (gesture.lastY - touch.clientY) / rowHeight;
    gesture.lastY = touch.clientY;
    const lines = Math.trunc(gesture.remainder);
    if (lines) {
      terminal.scrollLines(lines);
      gesture.remainder -= lines;
    }
  };
  host.addEventListener('touchstart', start, { passive: true });
  host.addEventListener('touchmove', move, { passive: false });
  host.addEventListener('touchend', reset);
  host.addEventListener('touchcancel', reset);
  terminal.attachCustomKeyEventHandler((event) => {
    if (
      event.type !== 'keydown' ||
      !event.shiftKey ||
      event.ctrlKey ||
      event.altKey ||
      event.metaKey
    )
      return true;
    switch (event.key) {
      case 'PageUp':
        terminal.scrollPages(-1);
        break;
      case 'PageDown':
        terminal.scrollPages(1);
        break;
      case 'Home':
        terminal.scrollToTop();
        break;
      case 'End':
        terminal.scrollToBottom();
        break;
      default:
        return true;
    }
    event.preventDefault();
    return false;
  });
  return () => {
    reset();
    host.removeEventListener('touchstart', start);
    host.removeEventListener('touchmove', move);
    host.removeEventListener('touchend', reset);
    host.removeEventListener('touchcancel', reset);
    terminal.attachCustomKeyEventHandler(() => true);
  };
};
