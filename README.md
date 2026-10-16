# gitops

## Pull request validation

The **Kustomize lint** workflow renders every tracked Kustomize overlay on
pull requests and pushes to `main`, and can also be run manually. It uses
kubectl v1.37.1's bundled Kustomize and Helm v3.19.0 with `--enable-helm`,
matching the Helm-enabled rendering required by Argo CD. A failed render
fails the check, while all overlays are still attempted for useful diagnostics.

This checks manifest composition and Helm rendering without cluster credentials
or applying resources. It does not check live-cluster readiness or validate
custom resources against installed CRD schemas. To reproduce a specific check
locally, run `kubectl kustomize <overlay-directory> --enable-helm` with Helm
available on your PATH.

## kubectl from another machine

Install Tailscale on the machine and sign in to this tailnet as the Kubernetes
user you want to use. Then generate a kubeconfig context for the API proxy:

```powershell
tailscale configure kubeconfig k3s-api.tailb11f97.ts.net
kubectl --context k3s-api.tailb11f97.ts.net auth whoami
kubectl --context k3s-api.tailb11f97.ts.net get nodes
```

This adds the Tailscale API proxy to that machine's kubeconfig. Kubernetes
permissions follow the signed-in Tailscale identity and its RBAC bindings; no
cluster-admin certificate needs to be copied between machines.

## ArgoCD Helm Support

The kube-prometheus-stack Kustomize build uses Helm chart inflation. Argo CD must be configured to pass `--enable-helm` to Kustomize through the `argocd-cm` ConfigMap. The `argocd/` overlay configures this with `kustomize.buildOptions`.

Apply the updated Argo CD overlay, then restart the repo-server so it picks up the build option:

Example for ArgoCD server deployment:
```powershell
kubectl apply -k argocd
kubectl rollout restart deployment/argocd-repo-server -n argocd
```

This setting applies to Kustomize builds performed by the Argo CD repo-server; `--enable-helm` is not an `argocd-server` command-line flag.

## Argo CD HTTPS access

The Argo CD UI is exposed at `https://argocd.ergoshear.dev` through Traefik.
ExternalDNS creates the public Route 53 record, and cert-manager issues the
TLS certificate with the `letsencrypt-prod` DNS-01 issuer. TLS terminates at
Traefik; Argo CD runs in insecure mode behind the ingress.

Apply the overlay and restart the server to load the configuration change:

```powershell
kubectl apply -k argocd
kubectl rollout restart deployment/argocd-server -n argocd
kubectl rollout status deployment/argocd-server -n argocd
```

## K3s API access over Tailscale

`apps/tailscale-operator/` installs the Tailscale Kubernetes Operator with its
in-process API server proxy. The proxy uses the `k3s-api` hostname and
authenticates requests as the connecting Tailscale identity; it does not grant
Kubernetes permissions by itself.

Before syncing the app:

- Enable MagicDNS and HTTPS certificates for the tailnet.
- Configure the tailnet ACL to allow the intended users or groups to reach
	`tag:k8s-operator` on TCP port 443. Ensure the operator tag can be assigned
	by the OAuth client and retain existing ownership rules for `tag:k8s`.
- Create a Tailscale OAuth client with write access to Services, Devices/Core,
	and Keys/Auth Keys, scoped to `tag:k8s-operator`.
- Create the `operator-oauth` Secret in the `tailscale` namespace with keys
	`client_id` and `client_secret` using the secure credential workflow. Do
	not commit OAuth credentials to this repository. Create the namespace first
	with `kubectl apply -f apps/tailscale-operator/namespace.yaml`.

After the operator is ready, find the `k3s-api` MagicDNS name in the Tailscale
admin console and run `tailscale configure kubeconfig <proxy-MagicDNS-name>`.
Grant the desired Kubernetes RBAC to the corresponding Tailscale login or
group separately; avoid granting cluster-admin to the whole tailnet.

## Fedora 44 Deployment

A Fedora 44 container deployment has been added to this GitOps setup. The deployment can be managed through ArgoCD and includes:

- A Kubernetes Deployment running Fedora 44 image
- A Service exposing the deployment
- An ArgoCD Application definition for managing the deployment

The deployment is structured with:
- `apps/base/` - Base manifests for Fedora 44 deployment
- `apps/hermes-agent/` - Overlay for Hermes agent configuration
- `apps/code-server/` - Standalone code-server deployment and persistent workspace

To deploy:
```powershell
kubectl apply -k apps
```

## VS Code in the browser

`https://code.ergoshear.dev` exposes stock `codercom/code-server:latest`,
replacing Pi Coder and Cockpit. The `vscode-service` Service is ClusterIP on
port 80, forwarding to code-server on port 8080, with TLS terminated at
Traefik. Password authentication is enabled; there is no Linux username login.
The container runs as UID/GID 1000 without privileged access or host mounts.

The deployment reuses the existing `pi-coder-login` Secret. Before syncing
`apps/code-server`, ensure this Secret exists in the
`agents` namespace with a nonempty `password` key. Use a protected local
file rather than putting the password in shell arguments or Git:

```sh
kubectl -n agents create secret generic pi-coder-login \
  --from-file=password=/path/to/protected/password-file
```

The password file must contain a single line. The pod requires this Secret
to start. Restart `vscode-web` after rotating the Secret to load the new
password.

The `vscode-pvc` ReadWriteOnce claim requests 100Gi using the cluster's default
StorageClass and persists `/home/coder/project`, the default workspace.
Settings and extensions outside this directory remain ephemeral. The
deployment uses `Recreate` to avoid concurrent pods sharing the workspace.
K3s local-path storage is node-local; ensure the selected node has sufficient
disk space. Its storage request is not a disk quota, and the current
StorageClass does not support volume expansion.

Argo CD's automated pruning removes the old Pi Coder Deployment and Service
when this replacement syncs. Copy any needed files out of the old ephemeral
Pi workspace before syncing. The stock image does not include the Pi CLI or
its model configuration. This also replaces the old `pi.ergoshear.dev`
ingress and certificate name; use `code.ergoshear.dev` after sync.

## Olla

`apps/olla/` deploys `ghcr.io/thushan/olla:latest` in the `agents` namespace,
with a ClusterIP Service on port 40114. The shared Traefik ingress, ExternalDNS,
and cert-manager certificate expose `https://olla.ergoshear.dev`.
The read-only dashboard is at `https://olla.ergoshear.dev/internal/ui/`, and
OpenAI-compatible clients can use `https://olla.ergoshear.dev/olla/openai/v1`.

Olla uses its native configuration, not LiteLLM's `model_list` schema.
`apps/olla/config.yaml` discovers the four in-cluster model Services and the
two Windows LM Studio servers listed below. The Qwen2.5 Coder endpoint uses
vLLM on port 8000; the in-cluster llama.cpp services use port 8080; LM Studio
serves on port 1234. Clients choose the model IDs advertised by `/v1/models`;
Hermes, n8n, and CrewAI request their configured model IDs. Olla uses
`least-connections` balancing.

The dashboard has no authentication. Its allowlist admits private-network
connections and the Olla hostname; behind Traefik it sees the proxy's address,
not the original client. Keep this ingress private like the other agent apps,
or add authentication at the ingress before making it publicly reachable.

## Model deployments

The following apps are included in `apps/kustomization.yaml` and Olla
discovery:

| App | Target node | Server | GPU allocation |
| --- | --- | --- | --- |
| `qwen25-coder-7b-instruct` | `mlops-node-2.lan` | vLLM, port 8000 | RTX 3080 Ti |
| `nomic-embed-text` | `mlops-node-3.lan` | llama.cpp, port 8080 | gfx1102 |
| `qwen36-27b` | `mlops-node-6.lan` | llama.cpp, port 8080 | RTX 4090 |
| `qwen38-27b` | `mlops-node-4.lan` | llama.cpp, port 8080 | gfx1201 |
| `lmstudio-node-7` | `mlops-node-7.lan` | LM Studio, port 1234 | Windows 11 |
| `lmstudio-node-9` | `mlops-node-9.lan` | LM Studio, port 1234 | Windows 11 |

Each app uses a node-bound local-path PVC, an init container to download and
pin the model, a single GPU request, and health probes. Nodes 2, 3, 4, and 6
each have a `dedicated=<model>:NoSchedule` taint, and each model pod tolerates
only its own node's taint. The GPU device plugins tolerate these taints.
Code-server and the n8n sandbox run on node 1 with new local-path claims. The
old claims remain for rollback; the node-7 model claim is retained but its
local data is unavailable while that node is removed. These taints do not evict
pods already running on the nodes. The single GPU request and one allocatable GPU
per node prevent a second GPU model from scheduling.
Grafana and Prometheus use new local-path volumes on node 0. Their previous
volumes on nodes 3 and 4 remain for rollback. Copy the data before syncing the
monitoring chart. Nodes 0 and 1 remain untainted for general workloads.
Publish each image to GHCR and verify GPU labels and device plugins before
syncing.
Validate Qwen3.8's 65K context and Q4_0 K/V cache on node 4, along with the
other model allocations on their target hardware.

The prior Llama 3.3 70B and Devstral Small 2 deployments and Services are
excluded from the root app list. Their PVCs remain managed by
`apps/retired-model-volumes/` so Argo CD pruning does not delete the model
files. Remove those claims separately only when the data is no longer needed.

## GPU device plugins

`apps/gpu-device-plugins/` deploys NVIDIA's device plugin to nodes labeled
`hardware.gpu=nvidia` and AMD's ROCm device plugin to nodes labeled
`hardware.gpu=amd`. Kubernetes then reports GPUs as extended resources
`nvidia.com/gpu` and `amd.com/gpu`; workloads request a GPU in their container
resource limits. The NVIDIA chart is pinned to 0.17.1. The AMD plugin is pinned
to 1.31.0.10 and gets host KFD/DRI access for device discovery. Neither plugin
installs or updates host kernel drivers; those remain managed by the node OS and
Salt.

The AMD model containers receive devices through Kubernetes instead of
privileged mode and direct host device mounts. Both GPU plugin DaemonSets
tolerate the dedicated model-node taints.
ConfigMap changes trigger a rollout through Kustomize's generated name hash.

## App image updates

The Hermes and n8n overlays track their respective
`ghcr.io/ergoshear` images with the `latest` tag and `imagePullPolicy: Always`.
New pods pull the current image. Publishing a new `latest` image does not
change the Deployment manifest or automatically restart existing pods;
restart the relevant Deployment after publishing to roll out the update.
Third-party app images and Helm-managed infrastructure retain their existing
version settings. Code-server tracks `codercom/code-server:latest` with
`imagePullPolicy: Always`; restart `vscode-web` to pick up a newly published
image.

### Hermes dashboard port

The Hermes overlay disables Kubernetes service-link environment variables and
explicitly sets `HERMES_DASHBOARD_PORT` to `"9119"`. Otherwise, the
`hermes-dashboard` Service injects `HERMES_DASHBOARD_PORT=tcp://<cluster-ip>:9119`,
which the s6 dashboard service passes to `--port`, causing an invalid integer
error. Service DNS discovery is unaffected. The dashboard Service and probes
continue to use port 9119, and dashboard authentication remains enabled.

## Agent DNS/TLS

K3s Traefik is the shared HTTPS entry point for `hermes-agent.ergoshear.dev`,
`n8n.ergoshear.dev`, `code.ergoshear.dev`, `olla.ergoshear.dev`, and
`argocd.ergoshear.dev`.
`apps/traefik-tailscale/` adds a separate LoadBalancer Service in `kube-system`
selecting the existing Traefik pods. Its `tailscale` loadBalancerClass makes
the Tailscale operator provision the `apps-ingress` proxy; the existing MetalLB
Service remains unchanged for LAN access.

ExternalDNS reads the five hostnames from this Service's hostname annotation
and publishes the Tailscale proxy IP from its `external-dns.kubernetes.io/target`
annotation. ExternalDNS was leaving the old LAN A records in place despite the
Tailscale IP appearing in LoadBalancer status, so this target is explicit. Keep
it in sync with the Service's Tailscale IP if that IP changes. This corrects
the public Route 53 A records from `192.168.202.104` without an A-to-CNAME
migration. The Ingresses do not opt into ExternalDNS; this Service is the
single DNS source for all five hostnames, avoiding competing LAN targets.

The operator publishes both a MagicDNS hostname and an IP in Service status.
ExternalDNS is restricted to managing A/AAAA records; the explicit target
annotation ensures it publishes the Tailscale IPv4 address rather than the
MagicDNS hostname or the Traefik LAN address. TXT registry ownership is still
managed automatically with the same `ergoshear-k3s` owner ID.

Public CNAMEs to MagicDNS names are deliberately avoided because they can fail
on Windows and Android clients; see
[tailscale/tailscale#7650](https://github.com/tailscale/tailscale/issues/7650).
App DNS resolution now uses ordinary public A records, but clients must still
connect to this tailnet to reach the IP. Configure ACLs/grants to permit clients to
reach `tag:k8s` on TCP ports 80 and 443; the operator's own `tag:k8s-operator`
API proxy is not the app endpoint. The public DNS records reveal the proxy's
tailnet IP but do not make it reachable from the internet. This is a single
proxy pod, so its restarts temporarily interrupt tailnet access.

The proxy forwards TCP to Traefik without terminating TLS. cert-manager still
obtains and renews the existing Let's Encrypt certificate using Route 53
DNS-01 challenges, and Traefik serves it for the original app hostnames. Use
the app URLs, not the proxy's MagicDNS hostname, for HTTPS.

Before applying, ensure a public Route 53 hosted zone for `ergoshear.dev` is
authoritative and create an AWS IAM identity with Route 53 permissions limited
to that zone. Create the controller namespaces, then create a Kubernetes Secret
named `route53-credentials` in both namespaces. Each Secret must contain the
keys `access-key-id` and `secret-access-key`. Do not commit AWS credentials to
this repository. The IAM policy in `apps/external-dns/route53-policy.json`
allows record changes throughout this hosted zone. ExternalDNS itself is
configured for the public `ergoshear.dev` zone, Services and Ingresses carrying
its opt-in annotation, A/AAAA records, and full `sync` reconciliation. It
updates changed records and removes stale records it owns when no opted-in
source requests them. cert-manager needs to create and remove TXT challenge
records in the same hosted zone.

Install cert-manager first so its CRDs exist before applying the ClusterIssuer
and Ingress resources:

```powershell
kubectl apply -f apps/cert-manager/namespace.yaml
kubectl apply -f apps/external-dns/namespace.yaml
# Create route53-credentials in both namespaces using your secure credential workflow.
kubectl kustomize apps/cert-manager --enable-helm | kubectl apply -f -
kubectl rollout status deployment/cert-manager -n cert-manager
kubectl kustomize apps --enable-helm | kubectl apply -f -
```

### Verify the Tailscale DNS cutover

After merging and syncing `apps`, wait for the proxy's IP and check
ExternalDNS reconciliation:

```sh
kubectl -n kube-system get service traefik-tailscale -o wide
kubectl -n external-dns logs deployment/external-dns --tail=50
dig +short A hermes-agent.ergoshear.dev
dig +short A n8n.ergoshear.dev
dig +short A code.ergoshear.dev
dig +short A olla.ergoshear.dev
dig +short A argocd.ergoshear.dev
```

Each A record should match both the Service's `target` annotation and its
Tailscale IPv4 address. Existing DNS caches may retain the previous address
until its TTL expires. From a tailnet
client, verify HTTPS to all five app URLs after propagation; before propagation
you can test with the original Host/SNI and the proxy's actual tailnet IP:

```sh
TAILSCALE_IP=$(kubectl -n kube-system get service traefik-tailscale \
  -o jsonpath='{.status.loadBalancer.ingress[?(@.ip)].ip}')
curl --resolve "code.ergoshear.dev:443:$TAILSCALE_IP" https://code.ergoshear.dev/
```

Also check `kubectl get ingress,certificate -n agents` and
`kubectl get challenges -A`. The Ingress status still shows the original
Traefik LAN LoadBalancer address; ExternalDNS now reads the proxy Service
instead. The Certificate must be Ready before HTTPS is available.

To roll back, revert the proxy Service and ExternalDNS source changes and
restore the app Ingress's ExternalDNS opt-in annotation. The same controller
owner ID allows it to reconcile the A records back to Traefik's LAN IP.
