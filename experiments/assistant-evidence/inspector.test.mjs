import test from 'node:test';
import assert from 'node:assert/strict';
import {projectEvidence, mountEvidence} from './inspector.mjs';
const tools = {read_record: {label: 'Read record', operation: 'read'}, update_record: {label: 'Update record', operation: 'write'}};
const options = {enabled: true, tools};
const event = {sequence: 1, tool: 'update_record', operation: 'write', status: 'attempted', records: [{type: 'deals', id: '42'}]};
test('disabled by default; no inference from a textual reply', () => {
  assert.equal(projectEvidence([event]), null);
  assert.deepEqual(projectEvidence({reply: 'Done'}, options).events, []);
});
test('preserves attempt, commit, rollback and unknown distinctions', () => {
  for (const [status, label] of [['attempted', 'Attempt observed'], ['committed', 'Commit confirmed'], ['rolled_back', 'Rolled back'], ['unknown', 'Outcome unknown']]) {
    assert.equal(projectEvidence([{...event, status}], options).events[0].status, label);
  }
  assert.equal(projectEvidence([{...event, status: 'completed'}], options).events.length, 0);
});
test('drops sensitive free text and malicious identifiers', () => {
  const projected = projectEvidence([{...event, arguments: 'SECRET', result_summary: 'SECRET', prompt: 'SECRET', records: [{type: 'deals', id: '42', label: 'SECRET'}, {type: 'deals', id: '<script>SECRET</script>'}]}], options);
  assert.ok(!JSON.stringify(projected).includes('SECRET'));
  assert.equal(projected.events[0].records.length, 1);
  assert.equal(projected.incomplete, true);
});
test('rejects unknown tools, mismatched kinds and non-monotonic sequences', () => {
  const projected = projectEvidence([event, event, {...event, sequence: 2, tool: 'invented'}, {...event, sequence: 3, operation: 'read'}], options);
  assert.equal(projected.events.length, 1);
  assert.equal(projected.incomplete, true);
});
test('bounds output and reports partial evidence', () => {
  const projected = projectEvidence(Array.from({length: 100}, (_, i) => ({...event, sequence: i + 1})), options);
  assert.equal(projected.events.length, 64);
  assert.equal(projected.incomplete, true);
});
test('request projections do not retain earlier evidence', () => {
  projectEvidence([event], options);
  assert.deepEqual(projectEvidence([], options).events, []);
});
test('renders collapsed text-only panel and clears it when disabled', () => {
  const doc = {createElement(tag) { return {tag, children: [], textContent: '', append(...nodes) {this.children.push(...nodes);}}; }};
  const container = {ownerDocument: doc, children: [], append(node) {this.children.push(node);}, replaceChildren() {this.children = [];}};
  mountEvidence(container, [event], options);
  assert.equal(container.children[0].tag, 'details');
  assert.match(container.children[0].children.map(n => n.textContent).join(' '), /Attempt observed/);
  mountEvidence(container, [event], {});
  assert.equal(container.children.length, 0);
  mountEvidence(container, undefined, options);
  assert.match(container.children[0].children.map(n => n.textContent).join(' '), /Evidence unavailable/);
});
