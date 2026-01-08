#!/bin/bash
# Quick start script for PRTS DB CLI

echo "=========================================="
echo "PRTS DB CLI - Quick Start"
echo "=========================================="

# Check if ChromaDB is running
echo ""
echo "[1/3] Checking ChromaDB connection..."
if curl -s http://localhost:9000/api/v1/heartbeat > /dev/null 2>&1; then
    echo "✓ ChromaDB is running"
else
    echo "✗ ChromaDB is not running!"
    echo ""
    echo "Please start ChromaDB first:"
    echo "  docker-compose up -d"
    exit 1
fi

# Check Python environment
echo ""
echo "[2/3] Checking Python environment..."
if [ -f "venv_py312/bin/python" ]; then
    PYTHON="venv_py312/bin/python"
    echo "✓ Using virtual environment: venv_py312"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    echo "✓ Using virtual environment: .venv"
else
    PYTHON="python"
    echo "⚠ Using system Python"
fi

# Check required modules
echo ""
echo "[3/3] Checking dependencies..."
if $PYTHON -c "import chromadb, langchain_chroma" > /dev/null 2>&1; then
    echo "✓ All dependencies installed"
else
    echo "✗ Missing dependencies!"
    echo ""
    echo "Please install requirements:"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Launch CLI
echo ""
echo "=========================================="
echo "Launching PRTS DB CLI..."
echo "=========================================="
echo ""

$PYTHON prts_db_cli.py
