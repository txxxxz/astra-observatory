# Observatory implementation ledger
Started 2026-11-05 10:56 Asia/Shanghai; 90-minute target, feature freeze 11:56, target handoff 12:26.
User plan is binding: FastAPI SQLite FULL WAL, React/TS/Vite/Three.js; full ingestion/query/export, real generator testing, Docker arm64.
Existing root repo has no commits and only user-provided untracked materials. New code isolated in observatory/; no history rewritten. Public repository/push requires later authorization.
API: docs/API.md is shared contract for backend/frontend/tests.
Tasks: backend + correctness; frontend + real Three.js; deployment + mixed-load harness; integration + browser QA + final docs.
Ruling: user mandates lightweight procedural nebula/Three.js, so visual assets are rendered in code and do not need external imagery.
- 10:58: Read original problem/generator instructions, all type messages, representative object and handoff. No applicable AGENTS.md found in ancestors. Docker live engine verified arm64, source image present.
- Parallel tasks use disjoint ownership (backend/tests; frontend; containers/scripts); developer parallelism guidance overrides sequential-only skill mechanics. Shared interfaces fixed in API.md.

- Independent review found export row-only chunk memory risk, SQLite variable-limit mismatch, raw _meta collision, and unrouteable run IDs. Added 8 reproducing failing cases; fixed byte-bound export, JSON-array subtree binding, explicit detail envelope and path-segment validation. Full33 tests pass.

- 11:20: Final host suite33/33 + Ruff passed; frontend TypeScript/Vite build passed with matching deployed JS hash. Docker33/33,3 mixed real-generator runs,4685 ACK batch audit afterSIGKILL and quick_check passed. Browser desktop/mobile workflows + streamed download +3000-point render verified. Source and evidence ready for local commit; public publication remains outside current authorization.
