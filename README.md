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