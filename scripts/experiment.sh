#!/usr/bin/env bash
# Compose down/up lifecycle; persist the deployed service list and resolved config.
set -euo pipefail
repository="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if (( $# != 1 )) || [[ "$1" != start && "$1" != stop && "$1" != status ]]; then
  echo '用法：bash scripts/experiment.sh {start|stop|status}' >&2
  exit 2
fi
action="$1"
docker compose version >/dev/null
if ! docker info >/dev/null; then
  echo '无法连接 Docker；请确认 Docker 已启动且当前用户有访问权限。' >&2
  exit 1
fi
state_dir="$repository/.local/experiment-lifecycle"
umask 077
mkdir -p "$state_dir"
projects=(gpu-alert-lab gpu-monitoring-ml gpu-rule-review npumonitor-rules-contract npumonitor-gpu-rules-master)
files=(nvidia-gpu/lab nvidia-gpu/ml nvidia-gpu/review nvidia-gpu/rules/reference nvidia-gpu/rules/production)
order=("${!projects[@]}")
if [[ "$action" == stop ]]; then
  order=()
  for (( i=${#projects[@]}-1; i>=0; i-- )); do order+=("$i"); done
fi
failed=0
found=0
for i in "${order[@]}"; do
  project="${projects[$i]}"
  compose=(docker compose --project-name "$project" --profile '*' -f "$repository/deploy/${files[$i]}/compose.yaml")
  if [[ "$project" == npumonitor-gpu-rules-master ]]; then
    # Match the local current-up deployment, including its shared lab network.
    compose=(env
      NPUMONITOR_RULES_PROJECT="$project"
      NPUMONITOR_RULES_CONFIG_DIR="$repository/.local/gpu-os-sre-master"
      NPUMONITOR_RULES_NETWORK=gpu-alert-lab_default
      NPUMONITOR_RULES_PORT=19476
      NPUMONITOR_N9E_TOKEN_FILE="$repository/.local/n9e-token"
      NPUMONITOR_NOTIFY_TOKEN_FILE="$repository/.local/gpu-os-sre-master/notify-token"
      "${compose[@]}" -f "$repository/deploy/nvidia-gpu/rules/current/compose.yaml")
  fi
  saved="$state_dir/$project"
  if [[ "$action" == status ]]; then
    echo "$project：status"
    if ! "${compose[@]}" ps --all; then failed=1; fi
    continue
  fi
  if ! service_names=$("${compose[@]}" ps --all --services); then
    echo "$project：查询失败。" >&2
    failed=1
    if [[ "$action" == stop ]]; then break; fi
    continue
  fi
  if [[ -n "$service_names" ]]; then
    # Preserve the existing ML simulation mode when resolving the Compose file.
    config_command=("${compose[@]}")
    if [[ "$project" == gpu-monitoring-ml ]]; then
      if ! ml_id=$("${compose[@]}" ps --all --quiet gpu-ml); then exit 1; fi
      if [[ -n "$ml_id" ]]; then
        if ! simulation=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$ml_id"); then exit 1; fi
        while IFS= read -r entry; do
          if [[ "$entry" == GPU_ML_SIMULATION=* ]]; then
            config_command=(env "$entry" "${compose[@]}")
          fi
        done <<< "$simulation"
      fi
    fi
    if ! "${config_command[@]}" config > "$saved.yaml.tmp"; then
      rm -f "$saved.yaml.tmp"
      echo "$project：保存启动配置失败，未删除容器。" >&2
      failed=1
      if [[ "$action" == stop ]]; then break; fi
      continue
    fi
    mv "$saved.yaml.tmp" "$saved.yaml"
    printf '%s\n' "$service_names" > "$saved.services.tmp"
    mv "$saved.services.tmp" "$saved.services"
  elif [[ ! -s "$saved.services" || ! -s "$saved.yaml" ]]; then
    echo "$project：没有已部署或已记录的实验服务，跳过；首次部署请使用模块 up 命令。"
    continue
  fi
  found=1
  echo "$project：$action"
  if [[ "$action" == stop ]]; then
    # Never add -v: named volumes must survive container/network removal.
    args=(down --timeout 60)
  else
    services=()
    while IFS= read -r service; do
      if [[ -n "$service" ]]; then services+=("$service"); fi
    done < "$saved.services"
    compose=(docker compose --project-name "$project" -f "$saved.yaml")
    args=(up -d --wait --wait-timeout 180 "${services[@]}")
  fi
  if ! "${compose[@]}" "${args[@]}"; then
    echo "$project：$action 失败，请检查后重试。" >&2
    failed=1
    # Leave the base network intact if removing a dependent project failed.
    break
  fi
  if [[ "$action" == stop ]]; then
    if ! remaining=$(docker ps --filter "label=com.docker.compose.project=$project" --format '{{.Names}}'); then
      echo "$project：无法确认容器是否已停止。" >&2
      failed=1
      break
    fi
    if [[ -n "$remaining" ]]; then
      printf '%s：仍有运行中的容器：\n%s\n' "$project" "$remaining" >&2
      failed=1
      break
    fi
  fi
done
if (( failed )); then exit 1; fi
if [[ "$action" == status ]]; then exit 0; fi
if (( ! found )); then
  echo '未发现已部署或已记录的实验服务。'
elif [[ "$action" == stop ]]; then
  echo '已通过 Compose down 删除实验容器；数据卷、镜像和本地文件保留，共用网络仍被占用时由 Docker 保留。'
else
  echo '已通过 Compose up -d 重建实验服务并通过就绪检查。'
fi
