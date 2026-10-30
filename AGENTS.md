# Jiuwen Ops Lab working rules

- Real model execution MUST use official Jiuwen Process SDK / CLI / Swarm Runtime / Core. Never introduce a scripted fake model as a product fallback.
- Product state, tool implementation, GitHub delivery and independent recovery verification belong to this repository. Keep those responsibilities separate.
- `.local/`, credentials, model request headers and complete container environment dumps must never enter Git or public evidence.
- Runner has no Docker socket or GitHub/control credential. Only the trusted engineering service merges/deploys under controller authorization.
- Repair candidates may change business code and add regression tests. They may not modify trusted workflows/contracts/deployment definitions.
- Preserve all existing experiment evidence and data by default. No broad Docker cleanup, VM deletion or volume deletion as routine recovery.
- Distinguish environment, engineering delivery and real-model Agent qualification in STATUS. Manual engineering acceptance must never report `RESOLVED_FIXED`.
- Validate product boundaries with `python -m unittest discover -s tests/product -v`; validate actual business behavior with `python scripts/ci.py --candidate . --trusted .` on Docker.
- Maintain README quickstart, RUNBOOK and official source/version links when interfaces change.

# Independent ADX experiment
- This is jiuwen-ops-adx-lab, separate from jiuwen-ops-lab. Never edit/restart/delete the old repository, VM, history or volumes as part of this project.
- Use a dedicated VM, Compose project, port range and public GitHub repository.
- Preserve the pinned official ADX activation and SDK execution chain; no direct Docker sandbox substitute.
- Keep platform credentials in control; sandbox execution credentials are per case/attempt and tool grants are server enforced.
- Distinguish environment qualification, minimal real execution, native observation and complete order incident acceptance.
