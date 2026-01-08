#!/bin/bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/src
python3 distill_knowledge.py --concurrency 15

