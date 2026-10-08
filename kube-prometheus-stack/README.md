# kube-prometheus-stack GitOps Deployment

This directory contains the GitOps configuration for deploying kube-prometheus-stack using ArgoCD and Helm.

## Files

- `helm-release.yaml` - Defines the HelmRelease resource for kube-prometheus-stack
- `helm-repository.yaml` - Defines the HelmRepository to fetch the chart from prometheus-community
- `kustomization.yaml` - Kustomization file for the deployment
- `values.yaml` - Helm values for configuring the kube-prometheus-stack chart

## Deployment

This configuration will deploy:
- Prometheus with 50Gi persistent storage
- Grafana with 10Gi persistent storage 
- Alertmanager with 120h retention
- Node exporter, kube-state-metrics, and other components

## Configuration

The deployment uses the prometheus-community Helm chart version 50.3.1.