/** Isolated, passive renderer. No fetch, storage, model calls or CRM mutations.
 * Input MUST be projected by the trusted dispatcher after authorization.
 * This validates shape, not authenticity. Never pass model-produced JSON here.
 */
const TYPES = new Set(['companies', 'contacts', 'deals', 'tickets', 'products', 'line_items', 'notes', 'calls', 'emails', 'meetings', 'tasks']);
const STATES = {
  read: new Set(['attempted', 'completed', 'failed']),
  write: new Set(['attempted', 'committed', 'rolled_back', 'unknown']),
};
const LABELS = {attempted: 'Attempt observed', completed: 'Read completed', failed: 'Read failed', committed: 'Commit confirmed', rolled_back: 'Rolled back', unknown: 'Outcome unknown'};

export function projectEvidence(input, {enabled = false, tools = {}} = {}) {
  if (enabled !== true) return null;
  const result = {events: [], incomplete: false};
  if (!Array.isArray(input)) return result;
  result.incomplete = input.length > 64;
  for (const event of input.slice(0, 64)) {
    if (!event || typeof event !== 'object' ||
        !Object.hasOwn(tools, event.tool) ||
        !['read', 'write'].includes(event.operation) ||
        tools[event.tool].operation !== event.operation ||
        !STATES[event.operation].has(event.status) ||
        !Number.isSafeInteger(event.sequence) || event.sequence < 1 ||
        (result.events.length && event.sequence <= result.events.at(-1).sequence)) {
      result.incomplete = true;
      continue;
    }
    const records = [];
    const source = Array.isArray(event.records) ? event.records : [];
    if (source.length > 20) result.incomplete = true;
    for (const record of source.slice(0, 20)) {
      if (record && TYPES.has(record.type) && typeof record.id === 'string' && /^[0-9]{1,20}$/.test(record.id)) {
        records.push({type: record.type, id: record.id});
      } else result.incomplete = true;
    }
    // Only fixed tool labels and authorized record identifiers survive projection.
    // Drop raw args, results, labels, prompts, errors, attachments, and unknown fields.
    result.events.push({sequence: event.sequence, tool: tools[event.tool].label,
      operation: event.operation, status: LABELS[event.status], records});
  }
  return result;
}

/** Mount only into the existing assistant message. Returns cleanup for React effects. */
export function mountEvidence(container, input, options) {
  container.replaceChildren();
  const evidence = projectEvidence(input, options);
  if (!evidence) return () => container.replaceChildren();
  const doc = container.ownerDocument;
  const panel = doc.createElement('details');
  const title = doc.createElement('summary');
  title.textContent = 'Assistant Evidence Inspector';
  panel.append(title);
  const add = text => { const p = doc.createElement('p'); p.textContent = text; panel.append(p); };
  add('Observed backend operations. This does not reveal model reasoning or prove which records caused an answer.');
  if (!evidence.events.length) add('Evidence unavailable for this reply. No conclusion about tool use or mutation success can be drawn.');
  for (const event of evidence.events) {
    add(`${event.sequence}. ${event.tool} · ${event.operation} · ${event.status}`);
    add(event.records.length ? `Records observed: ${event.records.map(r => `${r.type} #${r.id}`).join(', ')}` : 'Record evidence unavailable.');
  }
  if (evidence.incomplete) add('Partial trace: some events or records were omitted.');
  add('Calculation evidence unavailable in this prototype.');
  container.append(panel);
  return () => container.replaceChildren();
}
