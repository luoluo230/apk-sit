#!/usr/bin/env bash
set -euo pipefail
ROLE="build-ios"
JENKINS_MASTER_URL="http://127.0.0.1:8082"
NODE_NAME=""
AGENT_WORK_DIR="$HOME/jenkins-agent"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="$2"; shift 2 ;;
    --jenkins-master-url) JENKINS_MASTER_URL="$2"; shift 2 ;;
    --node-name) NODE_NAME="$2"; shift 2 ;;
    --work-dir) AGENT_WORK_DIR="$2"; shift 2 ;;
    *) shift ;;
  esac
done

label="build-ios"
name="${NODE_NAME:-ios-$(hostname -s)}"
mkdir -p "$AGENT_WORK_DIR"
jar="$AGENT_WORK_DIR/agent.jar"
if [[ ! -f "$jar" ]]; then
  curl -sf "${JENKINS_MASTER_URL%/}/jnlpJars/agent.jar" -o "$jar"
fi
cat <<EOF
[agent] Create Jenkins node:
  name=$name
  labels=$label
  workDir=$AGENT_WORK_DIR
  java -jar $jar -url $JENKINS_MASTER_URL -name $name -secret <SECRET> -workDir "$AGENT_WORK_DIR"
EOF
