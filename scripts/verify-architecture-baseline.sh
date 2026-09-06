#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/verify-architecture-baseline.sh [--architecture-repo PATH]
                                                [--implementation-root PATH]

Verify the implementation repository's recorded baseline, accepted addendum,
Git tags, immutable commits, and normative contract schema hash.

The architecture repository defaults to a sibling directory named
"wealthpilot-arch". WEALTHPILOT_ARCH_REPOSITORY may provide another local path.
EOF
}

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
implementation_root="$(dirname -- "$script_dir")"
architecture_repo="${WEALTHPILOT_ARCH_REPOSITORY:-$(dirname -- "$implementation_root")/wealthpilot-arch}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --architecture-repo)
      [ "$#" -ge 2 ] || { echo "missing value for --architecture-repo" >&2; exit 2; }
      architecture_repo="$2"
      shift 2
      ;;
    --implementation-root)
      [ "$#" -ge 2 ] || { echo "missing value for --implementation-root" >&2; exit 2; }
      implementation_root="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

metadata_json="$implementation_root/ARCHITECTURE_BASELINE.json"
metadata_yaml="$implementation_root/ARCHITECTURE_BASELINE"

[ -f "$metadata_json" ] || { echo "missing metadata: $metadata_json" >&2; exit 1; }
[ -f "$metadata_yaml" ] || { echo "missing metadata: $metadata_yaml" >&2; exit 1; }
git -C "$architecture_repo" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "not a Git architecture repository: $architecture_repo" >&2
  exit 1
}

metadata="$({ python3 - "$metadata_json" "$metadata_yaml" <<'PY'
import json
import re
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
yaml_path = Path(sys.argv[2])
data = json.loads(json_path.read_text(encoding="utf-8"))

required_top_level = {
    "schema_version",
    "architecture_repository",
    "implementation_repository",
    "baseline_name",
    "baseline_tag",
    "baseline_commit",
    "contract_addenda",
    "effective_architecture_commit",
    "recorded_at",
}
missing = sorted(required_top_level - data.keys())
if missing:
    raise SystemExit(f"ARCHITECTURE_BASELINE.json missing fields: {', '.join(missing)}")
if data["schema_version"] != "1.0.0":
    raise SystemExit("unsupported ARCHITECTURE_BASELINE.json schema_version")

sha_pattern = re.compile(r"[0-9a-f]{40}")
hash_pattern = re.compile(r"[0-9a-f]{64}")
tag_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
path_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
repository_pattern = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?")

architecture_repository = data["architecture_repository"]
if not isinstance(architecture_repository, str) or not repository_pattern.fullmatch(architecture_repository):
    raise SystemExit("architecture_repository must be a canonical GitHub HTTPS URL")
architecture_repository_yaml = architecture_repository.removesuffix(".git")

baseline_tag = data["baseline_tag"]
baseline_commit = data["baseline_commit"]
if not tag_pattern.fullmatch(baseline_tag):
    raise SystemExit("invalid baseline tag")
if not sha_pattern.fullmatch(baseline_commit):
    raise SystemExit("baseline commit must be a full lowercase SHA-1")

addenda = data["contract_addenda"]
if not isinstance(addenda, list) or len(addenda) != 1:
    raise SystemExit("M00/M01 metadata must contain exactly one accepted contract addendum")
addendum = addenda[0]
required_addendum = {
    "name",
    "schema_version",
    "repository_path",
    "schema_path",
    "git_tag",
    "git_commit",
    "schema_sha256",
}
missing = sorted(required_addendum - addendum.keys())
if missing:
    raise SystemExit(f"contract addendum missing fields: {', '.join(missing)}")
if addendum["schema_version"] != "1.0.0":
    raise SystemExit("unsupported contract addendum schema_version")
if not tag_pattern.fullmatch(addendum["git_tag"]):
    raise SystemExit("invalid addendum tag")
if not sha_pattern.fullmatch(addendum["git_commit"]):
    raise SystemExit("addendum commit must be a full lowercase SHA-1")
if not hash_pattern.fullmatch(addendum["schema_sha256"]):
    raise SystemExit("schema_sha256 must be 64 lowercase hexadecimal characters")
if not path_pattern.fullmatch(addendum["schema_path"]) or addendum["schema_path"].startswith("/"):
    raise SystemExit("schema_path must be a safe repository-relative path")
if data["effective_architecture_commit"] != addendum["git_commit"]:
    raise SystemExit("effective architecture commit must equal the latest accepted addendum commit")

# The YAML record is kept for humans; fail closed if it drifts from the
# machine-readable record used below.
yaml_text = yaml_path.read_text(encoding="utf-8")
expected_fragments = (
    f"architecture_repository: {architecture_repository_yaml}",
    f"  tag: {baseline_tag}",
    f"  commit: {baseline_commit}",
    f"    tag: {addendum['git_tag']}",
    f"    commit: {addendum['git_commit']}",
    f"    schema_sha256: {addendum['schema_sha256']}",
    f"effective_architecture_commit: {data['effective_architecture_commit']}",
)
for fragment in expected_fragments:
    if fragment not in yaml_text.splitlines():
        raise SystemExit(f"ARCHITECTURE_BASELINE drift: missing exact line {fragment!r}")

print(architecture_repository)
print(baseline_tag)
print(baseline_commit)
print(addendum["git_tag"])
print(addendum["git_commit"])
print(addendum["schema_path"])
print(addendum["schema_sha256"])
print(data["effective_architecture_commit"])
PY
} 2>&1)" || {
  echo "$metadata" >&2
  exit 1
}

architecture_repository="$(printf '%s\n' "$metadata" | sed -n '1p')"
baseline_tag="$(printf '%s\n' "$metadata" | sed -n '2p')"
baseline_commit="$(printf '%s\n' "$metadata" | sed -n '3p')"
addendum_tag="$(printf '%s\n' "$metadata" | sed -n '4p')"
addendum_commit="$(printf '%s\n' "$metadata" | sed -n '5p')"
schema_path="$(printf '%s\n' "$metadata" | sed -n '6p')"
schema_sha256="$(printf '%s\n' "$metadata" | sed -n '7p')"
effective_commit="$(printf '%s\n' "$metadata" | sed -n '8p')"

normalize_repository() {
  printf '%s' "$1" \
    | sed -E 's#^git@github\.com:#https://github.com/#; s#/$##; s#\.git$##'
}

recorded_repository="$(normalize_repository "$architecture_repository")"
origin_repository="$(git -C "$architecture_repo" remote get-url origin 2>/dev/null)" || {
  echo "architecture repository has no origin remote: $architecture_repo" >&2
  exit 1
}
origin_repository="$(normalize_repository "$origin_repository")"
[ "$origin_repository" = "$recorded_repository" ] || {
  echo "architecture repository identity mismatch: expected $recorded_repository, got $origin_repository" >&2
  exit 1
}

resolve_commit() {
  git -C "$architecture_repo" rev-parse --verify "$1^{commit}" 2>/dev/null
}

resolved_baseline="$(resolve_commit "refs/tags/$baseline_tag")" || {
  echo "baseline tag is missing or does not resolve to a commit: $baseline_tag" >&2
  exit 1
}
[ "$resolved_baseline" = "$baseline_commit" ] || {
  echo "baseline tag mismatch: expected $baseline_commit, got $resolved_baseline" >&2
  exit 1
}

resolved_addendum="$(resolve_commit "refs/tags/$addendum_tag")" || {
  echo "addendum tag is missing or does not resolve to a commit: $addendum_tag" >&2
  exit 1
}
[ "$resolved_addendum" = "$addendum_commit" ] || {
  echo "addendum tag mismatch: expected $addendum_commit, got $resolved_addendum" >&2
  exit 1
}
[ "$resolved_addendum" = "$effective_commit" ] || {
  echo "effective architecture commit mismatch: expected $effective_commit, got $resolved_addendum" >&2
  exit 1
}

actual_schema_sha256="$(git -C "$architecture_repo" show "$addendum_commit:$schema_path" | shasum -a 256 | awk '{print $1}')" || {
  echo "unable to read schema at $addendum_commit:$schema_path" >&2
  exit 1
}
[ "$actual_schema_sha256" = "$schema_sha256" ] || {
  echo "schema hash mismatch: expected $schema_sha256, got $actual_schema_sha256" >&2
  exit 1
}

printf '%s\n' \
  "Architecture baseline verified." \
  "  baseline: $baseline_tag -> $resolved_baseline" \
  "  addendum: $addendum_tag -> $resolved_addendum" \
  "  effective: $effective_commit" \
  "  schema sha256: $actual_schema_sha256"
