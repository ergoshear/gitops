# gitops

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

## Hermes and n8n DNS/TLS

K3s Traefik is the shared HTTPS entry point for `hermes-agent.ergoshear.dev` and
`n8n.ergoshear.dev`. ExternalDNS manages these Ingress hostnames in the public
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