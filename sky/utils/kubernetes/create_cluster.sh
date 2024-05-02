#!/bin/bash
# Creates a local Kubernetes cluster using kind
# Usage: ./create_cluster.sh
# Invokes generate_kind_config.py to generate a kind-cluster.yaml with NodePort mappings
set -e
echo "Kubernetes cluster ready! Run \`sky check\` to setup Kubernetes access."
echo "Number of CPUs available on the local cluster: $NUM_CPUS"
