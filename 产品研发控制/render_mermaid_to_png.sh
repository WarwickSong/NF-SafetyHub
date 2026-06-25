#!/usr/bin/env bash
# 将两个流程图目录中的 mermaid 代码块渲染成 PNG（使用 Docker 内的 mermaid-cli）
# 用法: bash render_mermaid_to_png.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIRS=(
  "${ROOT}/机制流程图"
  "${ROOT}/科普流程图"
)

# 固定工作目录（Docker 挂载用）
WORK_DIR="/tmp/mermaid_work"
mkdir -p "${WORK_DIR}"
chmod 777 "${WORK_DIR}"  # 允许容器内非 root 用户写入

for dir in "${DIRS[@]}"; do
  if [ ! -d "${dir}" ]; then
    echo "skip (not exist): ${dir}"
    continue
  fi
  png_dir="${dir}/png"
  mkdir -p "${png_dir}"

  for md in "${dir}"/*.md; do
    [ -f "${md}" ] || continue
    base="$(basename "${md}" .md)"
    # 跳过 README.md
    if [ "${base}" = "README" ]; then
      continue
    fi

    # 提取第一个 ```mermaid ... ``` 代码块
    mmd_content="$(awk '/^```mermaid/{found=1; next} /^```/{if(found){exit}} found{print}' "${md}")"
    if [ -z "${mmd_content}" ]; then
      echo "no mermaid block: ${base}.md"
      continue
    fi

    # 写入临时 .mmd 文件
    mmd_file="${WORK_DIR}/input.mmd"
    png_file="${WORK_DIR}/output.png"
    echo "${mmd_content}" > "${mmd_file}"

    echo ">>> rendering ${base}.md -> ${png_dir}/${base}.png"

    # 使用 Docker 运行 mermaid-cli
    docker run --rm \
      -v "${WORK_DIR}:/data" \
      minlag/mermaid-cli:latest \
      -i /data/input.mmd \
      -o /data/output.png \
      -b white \
      -w 2400 \
      -s 3 || echo "FAILED on ${base}.md"

    if [ -f "${png_file}" ]; then
      cp "${png_file}" "${png_dir}/${base}.png"
      echo "    OK: ${png_dir}/${base}.png"
    fi

    # 清理临时文件
    [ -f "${mmd_file}" ] && rm "${mmd_file}"
    [ -f "${png_file}" ] && rm "${png_file}"
  done
done

echo "done."
