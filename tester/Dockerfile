# Functional tester image for the Marketplace verification harness.
# It contains the public gRPC contract and grpcurl, but no TMR-WE runtime.
FROM fullstorydev/grpcurl:v1.9.3 AS grpcurl

FROM alpine:3.20
RUN adduser -D -u 10001 tester
COPY --from=grpcurl /bin/grpcurl /usr/local/bin/grpcurl
COPY api/tmrwe/v1/world_engine.proto /etc/tmrwe/world_engine.proto
USER 10001
ENTRYPOINT ["/bin/sh", "-c"]
