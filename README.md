# TMR World Engine — GKE Marketplace package

Deployment configuration for running **TMR World Engine (TMR-WE)** as an
authenticated gRPC service inside your own Google Kubernetes Engine cluster.

TMR-WE performs **deterministic replay** of a customer-supplied replay bundle
and **bounded counterfactual branching** over it. Replay is reproducible: the
same bundle yields the same semantic state digest on every run and on every
supported client.

## What is in this repository

This repository contains deployment configuration only:

| Path | Purpose |
| --- | --- |
| `chart/tmrwe/` | Helm chart, including the Marketplace `Application` resource |
| `deployer/` | Marketplace deployer image definition |
| `schema.yaml` | Marketplace parameter schema |
| `api/tmrwe/v1/` | Versioned gRPC service contract, for writing client code |
| `docs/user-guide.md` | Installation, operation, upgrade, and removal guide |
| `tests/` | Deployment integration test |

The TMR-WE runtime is **not** in this repository. It is distributed as a
container image under a separate proprietary runtime license. The
Apache-2.0 `LICENSE` here covers this deployment configuration and its
documentation only.

## Service boundary

The deployed service is **read-only with respect to your systems**. It
accepts a replay bundle, replays it, and returns results. It has no mutation
RPC, does not connect to your infrastructure, and does not require any
credential to your source systems. Domain data reaches TMR-WE only as a
bundle you construct and send.

The gRPC surface is: capability discovery, bundle validation, bundle replay,
streaming replay trace, and administrative TLS rotation. See
`api/tmrwe/v1/world_engine.proto`.

## Requirements

- A GKE cluster (Standard or Autopilot) with the Application CRD installed.
- Two pre-created Kubernetes Secrets: TLS material and an authentication
  token. Both are described in the user guide; neither is generated for you,
  by design.
- Client mutual-TLS certificates issued from your own CA.

## Install

Full instructions, including secret creation and parameter guidance, are in
[`docs/user-guide.md`](docs/user-guide.md). The short form:

```bash
helm install tmrwe ./chart/tmrwe \
  --namespace tmrwe \
  --create-namespace \
  --set existingTlsSecret=tmrwe-tls \
  --set existingAuthSecret=tmrwe-auth \
  --set image.repository=REGISTRY/tmrwe \
  --set image.tag=RELEASE_TAG
```

The chart refuses to install without both secrets rather than starting an
unauthenticated service.

## Release status

TMR-WE is at **controlled-pilot** status. Its deterministic replay core,
transport authentication, credential lifecycle, and upgrade/rollback paths
are covered by an automated regression suite and by executed remote-pilot
evidence. It is **not** yet declared production-ready: sustained multi-tenant
workload, high availability, disaster recovery, and long-duration remote soak
are not claimed. Evaluate it against your own acceptance criteria before
depending on it.

## Licensing

- Deployment configuration and documentation in this repository: Apache-2.0.
- TMR-WE runtime image: proprietary, licensed separately. The pilot uses a
  bring-your-own-license (BYOL) model; subscription terms are agreed
  directly with the vendor.

## Support

Report deployment issues through this repository. Runtime and licensing
questions go to the vendor contact named in your subscription agreement.
