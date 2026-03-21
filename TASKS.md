## Genesis Kernel [#genesis]

## Iteration 0: Foundation [#iter-0]

- [x] Build quick-task Python API module [#gen-build-qt-api]
    - [x] Create src/quick_task/api.py in quick-task repo [#gen-build-qt-api-module]
    - [x] load_file() convenience function [#gen-build-qt-api-load]
    - [x] get_task() wrapping matcher.find_task [#gen-build-qt-api-get]
    - [x] Re-export add_task, update_status, list_tasks [#gen-build-qt-api-reexport]
    - [x] Tests for API module in quick-task repo [#gen-build-qt-api-tests]
    - [x] CLI imports from API (thin wrapper) [#gen-build-qt-api-cli]
- [x] Create pyproject.toml with dependencies [#gen-pyproject]
    depends: #iter-0
    docs: docs/plans/2026-03-20-genesis-design.md#tech-stack
- [x] Create src/genesis package skeleton [#gen-skeleton]
    depends: #gen-pyproject
- [x] Set up pytest configuration and trivial test [#gen-pytest]
    depends: #gen-skeleton
- [x] Verify editable install of quick-task works [#gen-qt-import]
    depends: #gen-build-qt-api
## Iteration 1: Message Bus + State Machine [#iter-1]

- [x] Implement message bus [#gen-bus]
    depends: #iter-0
    docs: docs/plans/2026-03-20-genesis-design.md#message-bus
    - [x] Message dataclass and serialization [#gen-bus-model]
    - [x] publish() — write JSON file [#gen-bus-publish]
    - [x] query() — filter by agent, event, task [#gen-bus-query]
    - [x] Tests for message bus [#gen-bus-tests]
- [x] Implement state machine [#gen-state]
    depends: #gen-bus
    docs: docs/plans/2026-03-20-genesis-design.md#state-machine
    - [x] VALID_TRANSITIONS table [#gen-state-transitions]
    - [x] transition() with bus event publishing [#gen-state-transition]
    - [x] Invalid transition rejection [#gen-state-invalid]
    - [x] Tests for all transitions [#gen-state-tests]
## Iteration 2: Tools + Config [#iter-2]

- [x] Implement config loader [#gen-config]
    depends: #iter-1
    docs: docs/plans/2026-03-20-genesis-design.md#configuration
- [x] Create genesis.toml with bootstrap defaults [#gen-toml]
    depends: #gen-config
- [x] Implement task operations tool [#gen-tool-task]
    depends: #gen-build-qt-api
- [x] Implement file operations tool [#gen-tool-file]
    depends: #gen-config
- [x] Implement git operations tool [#gen-tool-git]
    depends: #gen-config
- [x] Implement test runner tool [#gen-tool-test]
    depends: #gen-config
- [x] Tests for all tools [#gen-tools-tests]
    depends: #gen-tool-test
## Iteration 3: Base Agent + Context [#iter-3]

- [x] Implement base agent LLM loop [#gen-agent-base]
    depends: #iter-2
    docs: docs/plans/2026-03-20-genesis-design.md#base-agent
    - [x] System prompt loading [#gen-agent-prompt]
    - [x] Tool dispatch [#gen-agent-tools]
    - [x] Budget tracking [#gen-agent-budget]
    - [x] Retry and error handling [#gen-agent-retry]
- [x] Implement context manager [#gen-context]
    depends: #gen-bus
    docs: docs/plans/2026-03-20-genesis-design.md#context-manager
- [x] Tests with mocked LLM [#gen-agent-tests]
    depends: #gen-context
## Iteration 4: Planner + Builder Agents [#iter-4]

- [x] Write planner system prompt [#gen-planner-prompt]
    docs: prompts/planner_system.md
- [x] Write builder system prompt [#gen-builder-prompt]
    docs: prompts/builder_system.md
- [x] Implement planner agent [#gen-planner]
    depends: #gen-planner-prompt
- [x] Implement builder agent [#gen-builder]
    depends: #gen-builder-prompt
- [x] Tests for planner and builder [#gen-agents-tests]
    depends: #gen-builder
## Iteration 5: Runner + End-to-End [#iter-5]

- [x] Implement genesis runner / orchestrator [#gen-runner]
    depends: #iter-4
    docs: docs/plans/2026-03-20-genesis-design.md#runner
- [x] Implement human gate mechanism [#gen-gates]
    depends: #gen-runner
- [x] End-to-end integration test (mocked LLM) [#gen-e2e-test]
    depends: #gen-runner
- [x] First real loop on quick-task improvement [#gen-first-loop]
    depends: #gen-e2e-test
    docs: spec/bootstrap-spec.md#the-first-project
## Token Efficiency [#token-efficiency]

- [x] Sliding window on message history
- [x] Truncate read_file tool output
- [ ] Truncate linked docs in context manager
- [ ] Remove duplicate tool descriptions from system prompt
## quick-task Improvements [#qt-improvements]

- [ ] Agent-oriented metadata fields [#qt-metadata]
    docs: spec/bootstrap-spec.md#agent-oriented-metadata
    - [ ] First-class fields: assignee, priority, created, updated [#qt-metadata-fields]
    - [ ] CLI flags: --assignee, --priority [#qt-metadata-cli]
    - [ ] Filter support: qt list --assignee @builder [#qt-metadata-filter]
- [ ] Transition history / audit log [#qt-history]
    docs: spec/bootstrap-spec.md#transition-history
    - [ ] Append history metadata on status change [#qt-history-append]
    - [ ] qt show --history display [#qt-history-show]
    - [ ] JSON output includes history [#qt-history-json]
- [ ] File locking for concurrent access [#qt-locking]
    docs: spec/bootstrap-spec.md#file-locking
    - [ ] Advisory lock on write [#qt-lock-acquire]
    - [ ] Stale lock detection [#qt-lock-stale]
- [ ] Filter/query enhancements [#qt-filters]
    docs: spec/bootstrap-spec.md#filter-query
    - [ ] Compound filter support [#qt-filter-compound]
    - [ ] --has-metadata filter [#qt-filter-metadata]
