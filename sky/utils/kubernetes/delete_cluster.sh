#!/bin/bash
# Script to delete the local kind cluster if it exists.
# Usage: ./delete_cluster.sh
# Raises error code 100 if the local cluster does not exist

set -e

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    >&2 echo "Error: Docker is not running. Please start Docker and try running the script again."
    exit 1
fi

# Check if kind is installed
if ! kind version > /dev/null 2>&1; then
    >&2 echo "Error: Kind is not installed. Please install kind and try running the script again."
    exit 1
fi

# Check if the local cluster exists
if ! kind get clusters | grep -q skypilot; then
    echo "Local cluster does not exist. Exiting."
    exit 100
fi

kind delete cluster --name skypilot
echo "Local cluster deleted!"

# Switch to the first available context
AVAILABLE_CONTEXT=$(kubectl config get-contexts -o name | head -n 1)
if [ ! -z "$AVAILABLE_CONTEXT" ]; then
    echo "Switching to context $AVAILABLE_CONTEXT"
    kubectl config use-context $AVAILABLE_CONTEXT
fi
