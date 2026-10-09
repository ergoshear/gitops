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