# AI Reliability Engine

@AGENTS.md

## Session boot and governance (applies to every session here)
- Governance home: kristian-os (PRINCIPLES -> GOVERNANCE ->
  FAILURE_REGISTER). Read before any irreversible action.
- Boot: read this repo's STATE.md first (if present; README status
  line otherwise); the operating contract (SPEC) loads globally.
- Before any write: environment fingerprint (pwd + git config
  user.email; /home/user/ path or noreply@anthropic.com = cloud
  sandbox = read-only, no pen). Pen check on main at open AND
  immediately before every commit.
- Close ritual: commit -> push origin main -> verify
  origin/main..HEAD empty -> report verbatim. Feature-branch push
  is not done.
- Work comes from the governance repo's queue (kristian-os,
  FABLE_QUEUE); do not invent tasks.
