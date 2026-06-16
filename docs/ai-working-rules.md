# AI Working Rules for This Project

## 🔴 CRITICAL — Read Before Every Session

### No Local Machine
The user **does not use a local machine at all.**

This means:
- ❌ Never say "run this on your machine"
- ❌ Never say "open a terminal"
- ❌ Never say "run this script locally"
- ❌ Never say "ssh-keygen on your machine"
- ❌ Never give `export VAR=value` shell instructions

Every action must be one of:
- ✅ **AI does it** — via GitHub MCP tools (create files, push commits, create workflows)
- ✅ **GitHub UI** — user clicks through github.com (Settings, Secrets, Actions)
- ✅ **Cloudflare Dashboard** — user clicks through dash.cloudflare.com
- ✅ **GitHub Actions** — workflow runs in CI, not locally

---

## SSH / Deploy Keys — How To Do It Without Local Machine

Standard `ssh-keygen` requires a terminal. Instead:

**Option A — GitHub Actions generates the key**
Create a one-shot workflow that runs `ssh-keygen` inside the runner,
prints the public key to logs, and saves the private key as a secret
via the GitHub API. User copies public key from logs into the target repo.

**Option B — Use GitHub's fine-grained personal access token instead of SSH**
For cross-repo checkout, a PAT with `contents: read` on the private repo
works without any key generation. User creates PAT in GitHub Settings →
Developer settings → Fine-grained tokens → set repo scope to learn09.

**Option C — GitHub App**
For production-grade cross-repo access without expiry concerns.

---

## Project Context

- **fyf-news-engine** — news pipeline (private)
- **learn09** — exam prep companion posts (private)
- **fyf-news-site** — Hugo news site (public) ← use for free Actions minutes
- **fyf-blog-site** — Hugo blog site
- All secrets live in GitHub repo secrets or Cloudflare dashboard
- Cloudflare services in use: Workers AI, Vectorize (index: `fyf-learn-links`), KV (`fyf-dedup`), R2

---

## Secret Naming Convention

| Secret Name | Where set | Purpose |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | repo secrets | CF account |
| `CLOUDFLARE_API_TOKEN` | repo secrets | CF Workers AI + Vectorize |
| `CLOUDFLARE_EMBEDDING_MODEL` | repo secrets | `@cf/baai/bge-small-en-v1.5` |
| `CF_KV_ACCOUNT_ID` | fyf-news-engine secrets | KV dedup |
| `CF_KV_API_TOKEN` | fyf-news-engine secrets | KV dedup |
| `CF_KV_NAMESPACE_ID` | fyf-news-engine secrets | KV dedup |
| `GEMINI_API_KEY` | fyf-news-engine secrets | Gemini AI |
| `NEWS_SITE_DEPLOY_KEY` | fyf-news-engine secrets | push to fyf-news-site |

---

*Last updated: 2026-06-16*
