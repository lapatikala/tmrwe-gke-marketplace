# Google Cloud Marketplace deployer image for TMR World Engine.
#
# This image contains ONLY deployment configuration: the Helm chart and the
# Marketplace parameter schema. It contains no TMR-WE runtime source code.
# The runtime itself ships as a separate application image referenced by
# image.repository / image.tag in values.yaml.
#
# Build from the repository root so the COPY paths below resolve:
#
#   docker build \
#     --tag "${REGISTRY}/deployer:${TAG}" \
#     --file deployer/Dockerfile \
#     .
#
# See docs/user-guide.md for the full build-and-publish sequence.

# Pin the Google Marketplace Helm deployer base by digest for reproducible
# packaging builds. The base image is published by Google's marketplace-k8s-app-tools.
FROM gcr.io/cloud-marketplace-tools/k8s/deployer_helm/onbuild@sha256:6a6d705987be9dacb976540b02901250bf09324c2fdc641f64c014da696bd198

COPY chart/tmrwe /data/chart/tmrwe
COPY schema.yaml /data/schema.yaml
