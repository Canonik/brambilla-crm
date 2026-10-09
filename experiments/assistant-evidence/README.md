# Isolated Assistant Evidence Inspector

Not integrated or deployed. Default off. No dependencies or model calls.
Read `docs/research/assistant-evidence-proposal.md` before considering integration.

Run local synthetic tests from this worktree:

```sh
node --test experiments/assistant-evidence/inspector.test.mjs
```

An approved host may import `mountEvidence` and call it for the existing chat reply container:

```js
// Proposed adapter example only; tool identifiers require Core approval.
const cleanup = mountEvidence(container, authorizedObservedEvents, {
  enabled: featureFlag === true,
  tools: {
    read_record: {label: 'Read record', operation: 'read'},
    update_record: {label: 'Update record', operation: 'write'},
  },
});
// Call cleanup on message disposal or logout.
```

`authorizedObservedEvents` must originate from the actual trusted backend dispatcher.
Never derive events/status from model text or pass raw tool payloads. A shape-valid event can
still be false or unauthorized; the component cannot establish its origin. Fixed labels are
trusted application configuration. IDs are accepted only after server authorization.
This is a UI component prototype, not a server sanitization or instrumentation implementation.
No fixtures are loaded by the component. Tests use synthetic events and a fake DOM.
