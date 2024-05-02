#!/bin/bash
# Builds the Dockerfile_k8s image as the SkyPilot image.
# Optionally, if -p is specified, pushes the image to the registry.
# Uses buildx to build the image for both amd64 and arm64.
# If -p flag is specified, pushes the image to the registry.
# If -g flag is specified, builds the GPU image in Dockerfile_k8s_gpu. GPU image is built only for amd64.
# Usage: ./build_image.sh [-p] [-g]
# -p: Push the image to the registry
# -g: Build the GPU image

TAG=us-central1-docker.pkg.dev/skypilot-375900/skypilotk8s/skypilot

push=false
gpu=false
push=false