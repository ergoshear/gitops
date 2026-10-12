#!/usr/bin/env bash
# Run from the gitops repository with: ./scripts/setup-github-runners.sh
set -euo pipefail

kubeconfig="${HOME}/.kube/config"
gitops_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -r "$kubeconfig" ]]; then
  printf 'Cannot read kubeconfig: %s\n' "$kubeconfig" >&2
  exit 1
fi

umask 077
token_file="$(mktemp "${TMPDIR:-/tmp}/arc-github-token.XXXXXX")"
cleanup() {
  rm -f "$token_file"
}
trap cleanup EXIT

printf '%s\n' 'ARC requires a GitHub PAT with organization runner permissions.' \
  'A one-time runner registration token will not work.'
read -r -s -p 'GitHub PAT: ' github_token
printf '\n'
if [[ -z "$github_token" ]]; then
  printf 'A token is required.\n' >&2
  exit 1
fi
printf '%s' "$github_token" > "$token_file"
unset github_token

kubectl --kubeconfig "$kubeconfig" create namespace github-runners \
  --dry-run=client -o yaml |
  kubectl --kubeconfig "$kubeconfig" apply -f -

kubectl --kubeconfig "$kubeconfig" -n github-runners \
  create secret generic github-runner-auth \
  --from-file=github_token="$token_file" \
  --dry-run=client -o yaml |
  kubectl --kubeconfig "$kubeconfig" apply -f -

rm -f "$token_file"
kubectl --kubeconfig "$kubeconfig" apply \
  -f "$gitops_dir/apps/github-runners/controller.yaml"
kubectl --kubeconfig "$kubeconfig" apply \
  -f "$gitops_dir/apps/github-runners/runners.yaml"
