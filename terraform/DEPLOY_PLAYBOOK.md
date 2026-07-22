# Deploy troubleshooting playbook

A runbook for when `.github/workflows/deploy.yml` doesn't do what it should. Read `README.md` first for what the pipeline is supposed to do -- this is what to do when it doesn't.

## How a deploy is supposed to go

1. Push to `main` touching `scraper/**` and/or the frontend paths (`app/**`, `utils/**`, `middleware.ts`, `next.config.ts`, `package.json`, `package-lock.json`, `Dockerfile`).
2. `changes` detects which side(s) changed.
3. Gates run for whichever side(s) changed: `test-backend` (pytest) + `typecheck` (mypy, via a `workflow_call` into `typecheck.yml`) + `dry-run-scrape` (a real, live `--dry-run` scrape, no DB writes) for the scraper; `test-frontend` (vitest) for the frontend.
4. If all relevant gates pass, `deploy-scraper` builds+pushes the scraper image and registers new task-definition revisions (the next EventBridge-scheduled run picks it up automatically -- no further action), and/or `deploy-frontend` builds+pushes the frontend image (App Runner auto-deploys the new `:latest`).
5. A push that changes nothing on a given side skips that side's gates and deploy job entirely (`if: needs.changes.outputs.<side> == 'true'`) -- that's expected, not a bug.

## How to verify a deploy actually landed

Green checkmarks in the Actions tab aren't sufficient proof by themselves -- confirm the real infra moved:

```bash
# Does the running task definition point at the commit you just pushed?
aws ecs describe-task-definition --task-definition used-cars-finder-scrape \
  --query 'taskDefinition.containerDefinitions[0].image' --output text
aws ecs describe-task-definition --task-definition used-cars-finder-notify \
  --query 'taskDefinition.containerDefinitions[0].image' --output text
# Should end in :<the commit sha you pushed>

git log --format=%H -1   # compare against the image tag above
```

For the frontend, load the App Runner URL (`terraform output apprunner_service_url`) and check for the change, or:

```bash
aws apprunner list-operations --service-arn <arn> --query 'OperationSummaryList[0].{Type:Type,Status:Status,StartedAt:StartedAt}'
```

**Don't trust a run's `conclusion` alone without also checking this** -- this project went a long time with every `deploy.yml` run failing silently (see below) while manual deploys made it look like things were working.

## Reading the GitHub API without a token

No `gh` CLI or PAT is assumed to be available in an agent/CI-debugging session. The unauthenticated REST API still works for a public repo, but is capped at **60 requests/hour per IP** -- burns fast if you poll on a tight loop. Lessons from hitting this wall mid-investigation:

- Check remaining quota before a polling loop: `curl -s https://api.github.com/rate_limit | python3 -m json.tool`
- Poll every 20-30s, not every 5-10s, for anything that takes minutes (a full deploy run does).
- Always check the actual HTTP status / response shape before parsing -- a rate-limited response is still valid JSON (`{"message": "API rate limit exceeded..."}`), so a naive `json.load(...)['status']` throws, and a bash loop that swallows that silently can spin forever printing nothing. Check for the `message`/`documentation_url` keys (or just check HTTP status via `-D -`) before assuming success.
- Job logs and repo variables/secrets require authenticated access (`403 Must have admin rights` for logs, `401` for variables) even on a public repo -- you can't read those without the user pasting them from the UI.

**Polling loops: don't capture-then-reinterpolate the JSON into a nested `python3 -c`.** A pattern like this looks reasonable but is fragile:

```bash
# BROKEN -- silently fails forever instead of erroring loudly
RESP=$(curl -s "$URL")
STATUS=$(echo "$RESP" | python3 -c "
import json,sys
try:
    print(json.load(sys.stdin).get('status','error'))
except Exception:
    print('parse_error')
")
```

Hit this twice in one session: real API responses (run objects, job lists) contain quotes, unicode, and other characters that break when a bash variable holding raw JSON gets re-embedded inside a heredoc-style `python3 -c "..."` string (worse with `'''$RESP'''`-style triple-quote interpolation -- any `'''` or backslash sequence already in the JSON corrupts the script). The broad `except Exception: print('parse_error')` swallows the real error instead of surfacing it, and if the poll loop's own logic treats `parse_error` as "still waiting," it spins **forever printing `parse_error`** even after the run actually finished -- burning the rate-limit budget on retries that can never succeed, and giving no signal that anything is wrong.

**Fix: pipe `curl` straight into `python3 -c` and read from stdin -- never round-trip through a bash variable:**

```bash
# ROBUST -- JSON never gets re-interpolated as a shell string
curl -s "$URL" | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('status', 'error'))
"
```

If you must inspect the value in bash afterward, redirect to a temp file instead of a variable (`curl -s "$URL" -o /tmp/resp.json`, then `python3 -c "..." < /tmp/resp.json`) -- still no shell re-interpolation of the JSON content. And regardless of which shape you use: if a poll loop ever logs the same unexplained status for more than 2-3 iterations, stop and run one `curl | python3` check directly rather than trusting the loop to self-correct.

Useful read-only queries:
```bash
# Recent runs of one workflow
curl -s "https://api.github.com/repos/<owner>/<repo>/actions/workflows/deploy.yml/runs?per_page=5" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(r['id'],r['head_sha'][:7],r['event'],r['status'],r['conclusion']) for r in d['workflow_runs']]"

# Job/step breakdown for one run
curl -s "https://api.github.com/repos/<owner>/<repo>/actions/runs/<run_id>/jobs" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(j['name'],j['conclusion']) for j in d['jobs']]"
```

## Known failure modes (all found the hard way, 2026-07-20/21)

### 1. `test-backend` fails on a test that passes locally

**Symptom**: a specific pytest test fails in CI, passes every time on your own machine.

**Likely cause**: the test depends on an absolute value of `time.monotonic()` (or similar OS-provided "time since some unspecified reference point"). That reference point is implementation-defined -- often system/container uptime -- so a long-uptime dev machine and a freshly-booted CI runner can disagree wildly. `test_bulk_save_throttles_progress_logging` hardcoded `last_log=0` assuming `time.monotonic()` would already exceed the test's interval; true on a machine that'd been up for hours, false on a fresh runner. This was invisible until `pytest` actually started running in CI (`test-backend` didn't exist before this pipeline).

**Fix pattern**: compute "far enough in the past" *relative to `time.monotonic()` called right there in the test* (e.g. `time.monotonic() - 10000`), never a hardcoded absolute value.

### 2. `configure-aws-credentials` fails with "Credentials could not be loaded... Could not load credentials from any providers"

**Symptom**: the step's printed `with:` block is missing `role-to-assume` entirely (only `aws-region`/`audience`/`output-env-credentials` show).

**Likely cause**: `role-to-assume: ${{ vars.AWS_GITHUB_ACTIONS_ROLE_ARN }}` resolved to empty. GitHub has two separate lists under **Settings → Secrets and variables → Actions**: **Secrets** and **Variables**. `vars.*` only reads the Variables tab. It's an easy mix-up to add the role ARN as a *secret* (nothing about it is actually sensitive -- it's just an ARN) instead of a *variable*, and the workflow will look identical except this one line silently goes empty.

**Fix**: Settings → Secrets and variables → Actions → **Variables** tab → add/confirm `AWS_GITHUB_ACTIONS_ROLE_ARN` = `terraform output github_actions_role_arn`'s value. Also confirm it's a **repository** variable, not scoped to an `environment:` the job doesn't declare.

### 3. `configure-aws-credentials` fails with "Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity"

**Symptom**: `role-to-assume` *is* populated correctly this time (you can see the real ARN in the log), but the actual AssumeRole call is rejected.

**Diagnosis**: check CloudTrail for the real rejected request -- this shows you the *actual* claims GitHub sent, not what you assume it sends:
```bash
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --start-time "$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ)" --max-results 5 \
  --query 'Events[].CloudTrailEvent' --output json \
  | python3 -c "import json,sys; [print(json.loads(e).get('userIdentity',{}).get('userName')) for e in json.load(sys.stdin)]"
```

**Root cause found here**: `iam.tf`'s trust policy condition expected the "classic" `repo:owner/name:ref:refs/heads/branch` sub-claim format (straight from the AWS/GitHub OIDC docs), but this GitHub account issues sub claims with owner/repo *names* suffixed by their immutable numeric IDs instead: `repo:owner@owner_id/name@repo_id:ref:refs/heads/branch`. The plain-name condition never matches, so every automated deploy since the initial AWS cutover failed here -- every real deploy up to that point had actually gone out via the manual `docker build`/`push`/`terraform apply` steps in `README.md`'s first-deployment log, not CI, even though the pipeline looked "done."

**Fix**: match the *actual* claim CloudTrail shows, not the docs' example format -- update `iam.tf`'s `StringLike` condition to the real value (see the comment there for the specific IDs this account uses). `terraform plan` should show exactly one change (the trust policy's `sub` condition); apply it, then re-verify against CloudTrail that the next attempt shows `errorCode` absent / a successful assume.

**If the repo is ever renamed or transferred**: these numeric IDs are stable across renames (that's the point of GitHub using them), but a transfer to a new owner or a full delete+recreate would change them -- re-run the CloudTrail check above to get the new values.

## General debugging approach

1. **Don't assume the newest failure is caused by your latest change.** Check the workflow's run history (`.../actions/workflows/deploy.yml/runs`) -- if every prior run also failed at the same step, it's a pre-existing, unrelated gap that just happened to get noticed now (this is exactly how #3 above was found: gating added visibility into a pipeline that had never worked).
2. **A generic SDK/action error message ("could not load credentials," "not authorized") is a summary, not the root cause.** Go to CloudTrail (or the equivalent for whatever's failing) for the real request/response before guessing.
3. **Verify fixes against the live resource, not just "terraform apply succeeded."** `aws iam get-role --query '...Condition'` after applying, not just trusting the plan matched intent.
4. **Re-check the actual pushed artifact after a "successful" deploy**, per the verification section above -- a green run and a real deployed change are two different claims.
