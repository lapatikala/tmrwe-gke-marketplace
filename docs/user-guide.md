# TMR World Engine — user guide

This guide covers installing, operating, upgrading, and removing TMR World
Engine (TMR-WE) on Google Kubernetes Engine.

## 1. Overview

TMR-WE is an authenticated gRPC service that performs deterministic replay
and bounded counterfactual branching over a replay bundle you supply.

Its defining property is reproducibility: replaying the same bundle always
produces the same semantic state digest, on every run and on every supported
client. That digest is what makes a replay result citable — you can compare
two runs, or two clients, and prove they agree.

### What it does

- **Validate** a replay bundle without executing it.
- **Replay** a bundle and return its semantic state digest, final checkpoint
  id, and trace ids.
- **Stream a replay trace**, emitting per-operation progress.
- **Rotate TLS material** on a running service, through an administrative
  credential separate from the replay credential.

### What it does not do

- It has **no mutation RPC**. It cannot write to anything.
- It does **not connect to your systems**. It never holds a credential to a
  source system; data reaches it only inside a bundle you send.
- It does **not deploy into, or control, other workloads** in your cluster.

## 2. Requirements

| Requirement | Notes |
| --- | --- |
| GKE cluster | Standard or Autopilot |
| Application CRD | Required by the Marketplace `Application` resource |
| Helm 3 | For direct chart installation |
| `kubectl` | Configured against the target cluster |
| TLS material | Server certificate/key plus the CA that signs client certificates |
| Auth token | A random secret used as the gRPC bearer token |
| Client certificates | Issued from your CA, for each approved client |

Install the Application CRD if your cluster does not already have it:

```bash
kubectl apply -f \
  "https://raw.githubusercontent.com/GoogleCloudPlatform/marketplace-k8s-app-tools/master/crd/app-crd.yaml"
```

## 3. Setup: create the required secrets

The chart deliberately does **not** generate credentials. It fails to install
if either secret is missing, so that a misconfigured install cannot silently
start an unauthenticated service.

### TLS secret

Must contain three keys: `server.crt`, `server.key`, and `client-ca.crt`.
`client-ca.crt` is the CA used to verify client certificates — this is what
enforces mutual TLS.

```bash
kubectl create namespace tmrwe

kubectl create secret generic tmrwe-tls \
  --namespace tmrwe \
  --from-file=server.crt=/path/to/server.crt \
  --from-file=server.key=/path/to/server.key \
  --from-file=client-ca.crt=/path/to/client-ca.crt
```

The server certificate must remain valid for at least 24 hours at startup;
the service refuses to start on material that expires sooner
(`--tls-min-validity-seconds=86400`). This is a guard against deploying an
already-expiring certificate, not a substitute for rotation.

### Authentication secret

Must contain a single key, `token`. Generate it with a CSPRNG and never reuse
it across environments:

```bash
umask 077
openssl rand -hex 32 > token

kubectl create secret generic tmrwe-auth \
  --namespace tmrwe \
  --from-file=token=./token

shred -u token   # or delete it securely on your platform
```

Do not commit either secret, and do not pass the token on a command line
where it would enter your shell history.

## 4. Install

```bash
helm install tmrwe ./chart/tmrwe \
  --namespace tmrwe \
  --set existingTlsSecret=tmrwe-tls \
  --set existingAuthSecret=tmrwe-auth \
  --set image.repository=REGISTRY/tmrwe \
  --set image.tag=RELEASE_TAG
```

### Parameters

| Parameter | Default | Guidance |
| --- | --- | --- |
| `image.repository` | — | Artifact Registry path holding the approved image |
| `image.tag` | `0.5.1` | Pin an immutable release tag; avoid floating tags |
| `service.type` | `ClusterIP` | Keep `ClusterIP` unless a reviewed network design requires otherwise |
| `service.port` | `50051` | gRPC port |
| `existingTlsSecret` | — | Required; see above |
| `existingAuthSecret` | — | Required; see above |
| `replicaCount` | `1` | See scaling, below |
| `resources.requests.cpu` | `250m` | Raise for larger bundles |
| `resources.requests.memory` | `256Mi` | Raise for larger bundles |
| `resources.limits.cpu` | `1` | Replay is CPU-bound |
| `resources.limits.memory` | `512Mi` | Bundle size drives peak memory |
| `networkPolicy.enabled` | `false` | Enable to restrict ingress to known clients |
| `networkPolicy.allowedClientCidrs` | `[]` | Required when the policy is enabled |

Exposing the service beyond `ClusterIP` puts a gRPC endpoint on a wider
network. Do that only with a reviewed network design; mutual TLS and the
bearer token are the only other barriers.

### Verify

```bash
kubectl get pods --namespace tmrwe
kubectl get application tmrwe --namespace tmrwe
```

The pod becomes ready once the gRPC port accepts connections. A pod that
never becomes ready usually indicates malformed or expiring TLS material —
check the container logs.

## 5. Basic usage

Clients connect over mutual TLS and present the bearer token as gRPC
metadata. Generate client stubs from `api/tmrwe/v1/world_engine.proto`.

Typical sequence:

1. `GetCapabilities` — confirm the API version and supported replay-bundle
   versions before sending anything else.
2. `ValidateReplayBundle` — check a bundle without executing it.
3. `ReplayBundle` — replay and receive the semantic state digest, final
   checkpoint id, and trace ids.
4. `ReplayBundleWithTrace` — the same replay, streaming per-operation trace
   updates.

Record the returned semantic state digest. Comparing digests across runs,
versions, or clients is how you verify that replay behaviour has not drifted.

### Health checks

The chart configures TCP readiness and liveness probes against the gRPC
port. Ready means the transport is accepting connections; it does not assert
that a specific bundle will replay successfully.

## 6. Scaling

Replay is stateless and CPU-bound: each request is self-contained, and no
state is shared between requests or replicas.

- **Horizontally**: raise `replicaCount`. Requests distribute across replicas
  and results stay identical, because replay is deterministic and stateless.
- **Vertically**: raise CPU and memory limits for larger bundles. Bundle size
  drives peak memory; a bundle that exceeds the memory limit fails that
  request rather than degrading the service.

Size limits against your own largest expected bundle before committing to a
value. The defaults suit bounded pilot bundles, not arbitrary workloads.

## 7. Certificate and token rotation

**TLS certificates** rotate on a running service without a restart, through
the administrative RPC, using a rotation credential distinct from the replay
token. New connections use the new certificate. Connections already
established continue on the old one until they close — plan rotation around
that, and do not treat an existing stream as proof of renegotiation.

**The bearer token** rotates by updating the auth Secret and restarting the
deployment:

```bash
kubectl create secret generic tmrwe-auth \
  --namespace tmrwe \
  --from-file=token=./new-token \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/tmrwe --namespace tmrwe
```

Distribute the new token to clients before restarting; clients using the old
token are rejected immediately after.

## 8. Backup and restore

The service is **stateless**. It holds no database and no persistent volume,
so there is nothing in the running service to back up.

What you must retain lives outside the cluster:

- your **replay bundles** — the actual inputs;
- your **recorded semantic state digests** — the evidence that a given bundle
  replayed to a given result;
- your **TLS material and tokens**, in your existing secret store.

Restore is therefore reinstallation: recreate the secrets, reinstall the
chart at the same pinned image tag, and replay a known bundle. If its digest
matches your recorded value, the restored service is behaving identically to
the one it replaced. That digest comparison is the restore verification —
run it deliberately, not just once.

## 9. Updating the image

```bash
helm upgrade tmrwe ./chart/tmrwe \
  --namespace tmrwe \
  --reuse-values \
  --set image.tag=NEW_RELEASE_TAG
```

After any upgrade, replay a known bundle and compare its semantic state
digest against the value recorded before the upgrade. An unchanged digest is
the evidence that replay semantics did not drift.

Roll back with:

```bash
helm rollback tmrwe --namespace tmrwe
```

then repeat the digest comparison. Rolling back the chart does not roll back
your secrets; if you rotated credentials since the previous release, they
remain rotated.

## 10. Uninstall and cleanup

```bash
helm uninstall tmrwe --namespace tmrwe
```

This removes the Deployment, Service, Application resource, and NetworkPolicy
if enabled. It does **not** remove the secrets you created, nor the
namespace:

```bash
kubectl delete secret tmrwe-tls tmrwe-auth --namespace tmrwe
kubectl delete namespace tmrwe
```

Deleting the namespace destroys the secrets in it. Confirm you have copies in
your own secret store first — the chart never generated them, so nothing else
holds a copy.

## 11. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `helm install` fails naming the secrets | `existingTlsSecret` or `existingAuthSecret` not set; the chart requires both |
| Pod never becomes ready | TLS material malformed, or the server certificate expires within 24 hours |
| Client rejected before any replay | Missing or wrong bearer token, or a client certificate not signed by `client-ca.crt` |
| Replay fails on one bundle only | Bundle malformed or version-incompatible; call `GetCapabilities` and `ValidateReplayBundle` |
| Replay fails on large bundles only | Memory limit too low for that bundle size |
| Digest differs after upgrade | Stop and investigate before proceeding; report it as a defect |

Container logs and audit records are payload-free by design: they record that
a request happened and how it ended, never bundle contents or credentials.
That is deliberate, and it means logs alone will not reconstruct a failing
bundle — keep the bundle that reproduced the problem.

## 12. Release status and support

TMR-WE is at **controlled-pilot** status. Deterministic replay, transport
authentication, credential lifecycle, and upgrade/rollback are covered by an
automated regression suite and executed remote-pilot evidence. Sustained
multi-tenant workload, high availability, disaster recovery, and
long-duration remote soak are **not** claimed.

Report deployment issues through this repository. Runtime and licensing
questions go to the vendor contact in your subscription agreement.
