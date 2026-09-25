# Ecosystem Ergonomics — Wave Handoffs

These handoffs organize execution of the sprint. The sole source of truth for
scope, decisions, GitHub issue numbers, acceptance, verification, and completed
wave records is [`../EXECUTION_CONTRACT.md`](../EXECUTION_CONTRACT.md).

| File | Purpose |
|---|---|
| [`AGENT_PLAYBOOK.md`](AGENT_PLAYBOOK.md) | Serial seven-wave workflow, gates, and handoff instructions |
| [`handoffs/WAVE-1.md`](handoffs/WAVE-1.md) … [`handoffs/WAVE-7.md`](handoffs/WAVE-7.md) | Working handoff notes; all state is transferred to the ledger at wave close |

One sprint branch is used throughout. No wave-specific implementation/test
branches or PRs are created. GitHub issues must be created and registered in
the ledger before Wave 1.
