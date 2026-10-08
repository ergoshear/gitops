# kube-prometheus-stack GitOps Deployment

This directory contains the GitOps configuration for deploying kube-prometheus-stack using ArgoCD and Helm.

## Files

- `kustomization.yaml` - Kustomization file for the deployment
- `values.yaml` - Helm values for configuring the kube-prometheus-stack chart

## Deployment

This configuration will deploy:
- Prometheus with 50Gi persistent storage
- Grafana with 10Gi persistent storage 
- Alertmanager with 120h retention
- Node exporter, kube-state-metrics, and other components

## Configuration

The deployment uses the prometheus-community Helm chart version 92.2.0.