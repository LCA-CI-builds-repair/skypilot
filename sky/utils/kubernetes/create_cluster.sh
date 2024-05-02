#!/bin/bash
# Creates a local Kubernetes cluster using kind
# Usage: ./create_cluster.sh
# Invokes generate_kind_config.py to generate a kind-cluster.yaml with NodePort mappings
set -e

# Limit port range to speed up kind cluster creation
PORT_RANGE_START=30000
PORT_RANGE_START=30100