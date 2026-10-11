#!/usr/bin/env bash
# Usage (from anywhere): AWS_PROFILE=<profile> deploy/aws/ecr-push.sh
# Builds deploy/Dockerfile.k8s for linux/amd64, pushes tagged by git SHA, prints the immutable digest.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REGION=ap-southeast-2; REPO=resolveflow
export AWS_DEFAULT_REGION=$REGION AWS_REGION=$REGION   # one explicit region for every aws call
ACCT=$(aws sts get-caller-identity --query Account --output text)
REG=$ACCT.dkr.ecr.$REGION.amazonaws.com
aws ecr describe-repositories --repository-names $REPO >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name $REPO --image-tag-mutability IMMUTABLE \
    --image-scanning-configuration scanOnPush=true
SHA=$(git -C "$ROOT" rev-parse --short HEAD)
aws ecr get-login-password | docker login --username AWS --password-stdin $REG
docker buildx build --platform linux/amd64 -f "$ROOT/deploy/Dockerfile.k8s" -t $REG/$REPO:$SHA --push "$ROOT"
aws ecr describe-images --repository-name $REPO --image-ids imageTag=$SHA --query 'imageDetails[0].imageDigest' --output text
