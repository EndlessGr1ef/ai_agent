#!/bin/bash
# Script to ingest both raw and distilled operator documents into unified collection

set -e

cd /Users/ts-chuanbo.song/Documents/AI/ai_agent
source .venv/bin/activate

echo "======================================================================"
echo "开始入库原始版干员文档到 prts_unified collection"
echo "======================================================================"
python ingest_md.py --docs-dir docs/prts/干员 --collection prts_unified

echo ""
echo "======================================================================"
echo "开始入库提炼版干员文档到 prts_unified collection"
echo "======================================================================"
python ingest_md.py --docs-dir docs/prts_distilled/干员 --collection prts_unified

echo ""
echo "======================================================================"
echo "✅ 全部入库完成！"
echo "======================================================================"
