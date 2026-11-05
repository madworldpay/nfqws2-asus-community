import assert from 'node:assert/strict';
const scroll = await import('../webui/web/src/utils/dpiTerminalScroll.ts').catch(() => ({}));
assert.equal(typeof scroll.bindDpiTerminalScrolling, 'function', 'native report must support touch and keyboard history scrolling');
class Host extends EventTarget {}
const host = new Host();
const actions = []; let keyboard;
const terminal = {
 rows: 28,
 element: {querySelector: () => ({getBoundingClientRect: () => ({height: 336})})},
 scrollLines: value => actions.push(['lines', value]),
 scrollPages: value => actions.push(['pages', value]),
 scrollToTop: () => actions.push(['top']),
 scrollToBottom: () => actions.push(['bottom']),
 attachCustomKeyEventHandler: handler => {keyboard = handler;},
};
const dispose = scroll.bindDpiTerminalScrolling(terminal, host);
const touch = (type, x, y, count=1) => {
 const event = new Event(type, {cancelable:true});
 Object.defineProperty(event, 'touches', {value:Array.from({length:count},()=>({clientX:x,clientY:y}))});
 host.dispatchEvent(event);return event.defaultPrevented;
};
touch('touchstart', 100, 100);
assert.equal(touch('touchmove', 101, 64), true);
assert.deepEqual(actions, [['lines',3]], 'one vertical swipe scrolls report history by actual row height');
touch('touchmove',101,40);
assert.deepEqual(actions.at(-1), ['lines',2]);
touch('touchend',0,0,0);
touch('touchstart',100,100);
assert.equal(touch('touchmove',145,102),false,'horizontal pan remains available for wide native tables');
assert.equal(touch('touchmove',160,55),false,'an established horizontal pan must not turn into vertical history scrolling');
const before=actions.length;
touch('touchstart',100,100,2);assert.equal(touch('touchmove',100,50,2),false);assert.equal(actions.length,before,'pinch is left to browser');
const key=(key,shift=true,type='keydown')=>{let prevented=false;const allowed=keyboard({key,shiftKey:shift,type,ctrlKey:false,altKey:false,metaKey:false,preventDefault(){prevented=true;}});return {allowed,prevented};};
assert.deepEqual(key('PageUp'),{allowed:false,prevented:true});assert.deepEqual(actions.at(-1),['pages',-1]);
key('PageDown');assert.deepEqual(actions.at(-1),['pages',1]);
key('Home');assert.deepEqual(actions.at(-1),['top']);key('End');assert.deepEqual(actions.at(-1),['bottom']);
assert.deepEqual(key('ArrowUp',false),{allowed:true,prevented:false},'native menu navigation must still reach Detector');
const last=actions.length;key('PageUp',true,'keyup');assert.equal(actions.length,last,'key-up must not scroll a second page');
dispose();touch('touchstart',100,100);touch('touchmove',100,40);assert.equal(actions.length,last,'unmounted terminal must release touch handlers');
console.log('PASS vertical swipe, horizontal pan, pinch, history keys, native navigation and disposal');
