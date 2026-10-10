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
- `apps/pi-coder/` - Overlay for Pi Coder configuration

To deploy:
```powershell
kubectl apply -k apps
```

## Pi Coder Cockpit

`https://pi.ergoshear.dev` exposes Cockpit's terminal for the Pi Coder
container. Log in as `pi`; this account has passwordless sudo inside the
container. The internal SSH server listens on loopback only, and the
Cockpit Service is ClusterIP with TLS terminated at Traefik.

Before syncing `apps/pi-coder`, create the `pi-coder-login` Secret in the
`agents` namespace with a nonempty `password` key. Use a protected local
file rather than putting the password in shell arguments or Git:

```sh
kubectl -n agents create secret generic pi-coder-login \
  --from-file=password=/path/to/protected/password-file
```

The password file must contain a single line. The pod requires this Secret
to start. Restart the deployment after rotating the Secret to apply the
new password to the Linux account. Pi's workspace and home directory are
currently ephemeral.

Merge and successfully publish the Cockpit-enabled `ergoshear/pi-coder`
image before syncing this overlay.

## Olla

`apps/olla/` deploys `ghcr.io/thushan/olla:latest` in the `agents` namespace,
with a ClusterIP Service on port 40114. The shared Traefik ingress, ExternalDNS,
and cert-manager certificate expose `https://olla.ergoshear.dev`.
The read-only dashboard is at `https://olla.ergoshear.dev/internal/ui/`, and
OpenAI-compatible clients can use `https://olla.ergoshear.dev/olla/openai/v1`.

Olla uses its native configuration, not LiteLLM's `model_list` schema.
`apps/olla/config.yaml` discovers models from Ollama at `192.168.1.10:11434`
and LM Studio at `192.168.1.12:1234`, using `least-connections` balancing
(the equivalent of least-busy). The `llama3` alias accepts Ollama's
`llama3:latest` and LM Studio's `llama3`; update it if LM Studio advertises
a different model ID. The `lm-studio` bearer token is the supplied placeholder,
not a production secret. Real credentials must be provided through a Kubernetes
Secret rather than committed to Git.

The dashboard has no authentication. Its allowlist admits private-network
connections and the Olla hostname; behind Traefik it sees the proxy's address,
not the original client. Keep this ingress private like the other agent apps,
or add authentication at the ingress before making it publicly reachable.
ConfigMap changes trigger a rollout through Kustomize's generated name hash.

## App image updates

The Hermes, Pi Coder, and n8n overlays all track their respective
`ghcr.io/ergoshear` images with the `latest` tag and `imagePullPolicy: Always`.
New pods pull the current image. Publishing a new `latest` image does not
change the Deployment manifest or automatically restart existing pods;
restart the relevant Deployment after publishing to roll out the update.
Third-party app images and Helm-managed infrastructure retain their existing
version settings.

## Agent DNS/TLS

K3s Traefik is the shared HTTPS entry point for `hermes-agent.ergoshear.dev`,
`n8n.ergoshear.dev`, and `pi.ergoshear.dev`. ExternalDNS manages these Ingress hostnames in the public
Route 53 hosted zone, and cert-manager obtains and renews a Let's Encrypt
certificate using Route 53 DNS-01 challenges. The public A records resolve to
Traefik's private MetalLB address, so the applications remain reachable only
from networks that can route to the cluster LAN. The private IP is visible in
public DNS.

Before applying, ensure a public Route 53 hosted zone for `ergoshear.dev` is
authoritative and create an AWS IAM identity with Route 53 permissions limited
to that zone. Create the controller namespaces, then create a Kubernetes Secret
named `route53-credentials` in both namespaces. Each Secret must contain the
keys `access-key-id` and `secret-access-key`. Do not commit AWS credentials to
this repository. The IAM policy in `apps/external-dns/route53-policy.json`
allows record changes throughout this hosted zone. ExternalDNS itself is
configured for the public `ergoshear.dev` zone, Ingresses carrying its opt-in
annotation, and upsert-only changes. cert-manager needs to create and remove
TXT challenge records in the same hosted zone.

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

After sync, check `kubectl get ingress,certificate -n agents` and
`kubectl get challenges -A`. The Ingress address should match the Traefik
LoadBalancer address, and the Certificate should become Ready before HTTPS is
available.