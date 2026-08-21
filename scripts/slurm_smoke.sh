#!/usr/bin/env bash
# slurm_smoke.sh — ComputePilot real-cluster Slurm smoke test (independent of CI).
#
# Validates the full sbatch/sacct/scancel chain a SlurmExecutor relies on.
# Usage:
#   ./scripts/slurm_smoke.sh            # run all checks
#   ./scripts/slurm_smoke.sh -v         # verbose
#
# Exit codes: 0 = all PASS, 1 = at least one FAIL, 2 = prerequisites missing.

set -u

VERBOSE=0
[[ "${1:-}" == "-v" ]] && VERBOSE=1

PASS=0
FAIL=0
JOB_IDS=()

check() { # check <name> <command...>
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name"
    FAIL=$((FAIL + 1))
  fi
}

section() { echo; echo "== $1 =="; }

# --- 0. Prerequisites -------------------------------------------------------
section "Prerequisites"
for cmd in sbatch squeue sacct scancel sinfo; do
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "  OK    $cmd found"
  else
    echo "  MISS  $cmd not in PATH"
    exit 2
  fi
done

sinfo --noheader 2>/dev/null | head -3 || true

WORKDIR=$(mktemp -d /tmp/cpilot_slurm_smoke.XXXXXX)
trap 'rm -rf "$WORKDIR"' EXIT

# --- 1. Basic batch job ------------------------------------------------------
section "Basic batch job (echo)"
cat > "$WORKDIR/basic.sbatch" <<'EOF'
#!/bin/bash
#SBATCH --job-name=cpilot_smoke_basic
#SBATCH --output=%x-%j.out
#SBATCH --time=00:02:00
#SBATCH --mem=256M
echo "hello from $(hostname)"
EOF
if job=$(sbatch --parsable "$WORKDIR/basic.sbatch" 2>&1); then
  JOB_IDS+=("$job")
  echo "  OK    submitted job $job"
else
  echo "  FAIL  sbatch submission: $job"
  exit 1
fi

# Wait for terminal state via sacct
wait_terminal() {
  local jid="$1" i
  for i in $(seq 1 60); do
    state=$(sacct -j "$jid" --format=State --noheader --parsable2 2>/dev/null | tail -1)
    case "$state" in
      COMPLETED|FAILED|CANCELLED|TIMEOUT|OUT_OF_*) echo "$state"; return 0 ;;
    esac
    sleep 2
  done
  echo "UNKNOWN"
}

state=$(wait_terminal "$job")
check "basic job reaches COMPLETED (got: ${state:-none})" test "$state" = "COMPLETED"

out_file="$WORKDIR/basic-${job}.out"
[[ -f "$out_file" ]] || out_file=$(ls "$WORKDIR"/basic-*.out 2>/dev/null | head -1)
check "job stdout file exists" test -n "${out_file:-}" && grep -q "hello from" "$out_file"

# --- 2. Environment / resource flags ----------------------------------------
section "Resource flags accepted by scheduler"
cat > "$WORKDIR/res.sbatch" <<'EOF'
#!/bin/bash
#SBATCH --job-name=cpilot_smoke_res
#SBATCH --cpus-per-task=2
#SBATCH --mem=512M
#SBATCH --time=00:01:00
echo ok
EOF
if res_job=$(sbatch --parsable "$WORKDIR/res.sbatch" 2>&1); then
  JOB_IDS+=("$res_job")
  check "--cpus-per-task/--mem accepted" true
else
  echo "  FAIL  resource flags rejected: $res_job"
  FAIL=$((FAIL + 1))
fi

# --- 3. scancel ---------------------------------------------------------------
section "Cancellation (scancel)"
cat > "$WORKDIR/sleep.sbatch" <<'EOF'
#!/bin/bash
#SBATCH --job-name=cpilot_smoke_sleep
#SBATCH --time=00:10:00
sleep 600
EOF
if sleep_job=$(sbatch --parsable "$WORKDIR/sleep.sbatch" 2>&1); then
  JOB_IDS+=("$sleep_job")
  sleep 3
  check "scancel accepted for running/pending job $sleep_job" scancel "$sleep_job"
  sleep 3
  cstate=$(sacct -j "$sleep_job" --format=State --noheader --parsable2 2>/dev/null | tail -1)
  [[ $VERBOSE -eq 1 ]] && echo "        post-cancel state: ${cstate:-none}"
  check "job shows CANCELLED* state (got: ${cstate:-none})" bash -c "[[ '${cstate:-}' == CANCELLED* ]]"
fi

# --- 4. sacct field coverage used by SlurmExecutor ---------------------------
section "sacct fields used by executor"
if [[ ${#JOB_IDS[@]} -gt 0 ]]; then
  fields=$(sacct -j "$(IFS=,; echo "${JOB_IDS[*]}")" \
    --format=JobID,State,Elapsed,ExitCode,MaxRSS --noheader --parsable2 2>/dev/null)
  [[ $VERBOSE -eq 1 ]] && echo "$fields" | head -5
  check "JobID/State/Elapsed/ExitCode parseable" test -n "$fields"
else
  echo "  SKIP  no jobs submitted"
fi

# --- Summary ------------------------------------------------------------------
echo
echo "== Summary: $PASS passed, $FAIL failed =="
[[ $FAIL -eq 0 ]]
