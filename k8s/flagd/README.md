# flagd deployment

`flags.json` is the single source of truth for both Kubernetes and local Docker
Compose. Do not add an independently maintained ConfigMap payload.

Validate and render the manifests before promotion:

```shell
kubectl kustomize k8s/flagd
```

Apply the reviewed GitOps revision with Kustomize support enabled:

```shell
kubectl apply -k k8s/flagd
```

Kustomize generates the stable `flagd-flags` ConfigMap consumed by the
Deployment. flagd watches the projected `flags.json` file and applies valid
updates without a backend restart.
