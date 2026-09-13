import assert from 'node:assert/strict';
import test from 'node:test';

import { SelectionObserver } from '../../src/interaction/selection-observer.ts';

test('selection observer registers once, coalesces triggers, and disposes', () => {
  let callback: (() => void) | undefined; let scheduled: (() => void) | undefined;
  let refreshSignals = 0; let removals = 0;
  const observer = new SelectionObserver({
    register: (value) => { callback = value; return true; },
    remove: () => { removals += 1; return true; },
    onDebouncedChange: () => { refreshSignals += 1; },
    schedule: (value: () => void) => { scheduled = value; return 1; }, clear: () => undefined,
  });
  assert.equal(observer.start(), true); assert.equal(observer.start(), false);
  assert.ok(callback); callback(); callback(); assert.ok(scheduled); scheduled();
  assert.equal(refreshSignals, 1);
  observer.dispose(); observer.dispose(); assert.equal(removals, 1);
});

test('event payload is never accepted as an observation', () => {
  const source = SelectionObserver.toString();
  assert.doesNotMatch(source, /eventPayload|primitiveIds/);
});

test('scheduled callback from a disposed generation cannot emit a refresh', () => {
  let callback: (() => void) | undefined; let scheduled: (() => void) | undefined;
  let refreshSignals = 0;
  const observer = new SelectionObserver({
    register: (value) => { callback = value; return true; },
    remove: () => true,
    onDebouncedChange: () => { refreshSignals += 1; },
    schedule: (value: () => void) => { scheduled = value; return 1; }, clear: () => undefined,
  });
  observer.start(); callback?.(); observer.dispose();
  scheduled?.();
  assert.equal(refreshSignals, 0);
});

test('callback retained by a previous listener generation is ignored after restart', () => {
  const callbacks: Array<() => void> = []; let schedules = 0;
  const observer = new SelectionObserver({
    register: (value) => { callbacks.push(value); return true; },
    remove: () => true,
    schedule: () => { schedules += 1; return schedules; }, clear: () => undefined,
  });
  observer.start(); observer.dispose(); observer.start();
  callbacks[0]?.();
  assert.equal(schedules, 0);
  callbacks[1]?.();
  assert.equal(schedules, 1);
});

test('debounced authoritative refresh signal is emitted at the stabilization boundary', () => {
  let callback: (() => void) | undefined; let scheduled: (() => void) | undefined;
  let refreshSignals = 0;
  const observer = new SelectionObserver({
    register: (value) => { callback = value; return true; },
    remove: () => true,
    onDebouncedChange: () => { refreshSignals += 1; },
    schedule: (value: () => void) => { scheduled = value; return 1; }, clear: () => undefined,
  });
  observer.start(); callback?.(); scheduled?.();
  assert.equal(refreshSignals, 1);
});

test('selection stabilization emits only the authoritative refresh trigger', () => {
  let callback: (() => void) | undefined; let scheduled: (() => void) | undefined;
  let refreshSignals = 0;
  const observer = new SelectionObserver({
    register: (value) => { callback = value; return true; },
    remove: () => true,
    onDebouncedChange: () => { refreshSignals += 1; },
    schedule: (value: () => void) => { scheduled = value; return 1; }, clear: () => undefined,
  });

  observer.start(); callback?.(); callback?.(); scheduled?.();

  assert.equal(refreshSignals, 1);
  assert.doesNotMatch(SelectionObserver.toString(), /readCurrentSelection|freshRead|submitObservation/);
});
