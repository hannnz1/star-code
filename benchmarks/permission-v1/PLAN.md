# Permission workflow replay v1

This is a deterministic production-policy replay, not a real model coding-session benchmark. Freeze ten distinct synthetic action traces before measurement. Replay read/search, edits, build/test/status, package operations and high-risk actions. Never execute shell actions in this benchmark. All commands, paths and intended risks are visible in the fixture.

BASELINE uses Star Code DEFAULT mode, automatic readonly access, unchanged path/blacklist/rule checks, and explicit ALLOW_ONCE for each safe write/command confirmation. CURRENT uses the same implementation/mode/rules and an injected user choosing ALLOW_SESSION for those confirmations. Both user policies deny high-risk actions. This comparison measures explicit session-grant reuse, not old-versus-new risk classifiers or autonomous model success. Session grants require a real user choice in the product; benchmark injection is disclosed.

Record every request/decision/source, whether a prompt occurred, approvals/denials, session grants, unsafe automatic approvals, wall time, seed20260905 and implementation/build/fixture hashes. Model/protocol/usage are NOT_APPLICABLE; task_success is null because no code is executed. Repeated same-path edits may reuse a scoped grant; different commands, remote arguments, actors, Worktree cwd and permission modes cannot. New sessions and resume clear grants; blacklist and path checks precede reuse. A deliberate user session grant can authorize later identical calls, so this is not an unconditional guarantee that all risky calls always prompt.

No30-to-5 target. No OS sandbox or five-layer claim. High-risk corpus is finite and cannot establish containment against arbitrary shell commands. Full tests and raw trace records must accompany the report.
