import os
import asyncio
import argparse
import time
from pathlib import Path
from typing import List, Dict, Any
from src.rag.distiller import KnowledgeDistiller

async def process_file(distiller: KnowledgeDistiller, input_path: Path, output_path: Path, semaphore: asyncio.Semaphore):
    """Process a single file with LLM distillation."""
    async with semaphore:
        try:
            # Skip if already exists and input not newer
            if output_path.exists() and output_path.stat().st_mtime >= input_path.stat().st_mtime:
                # print(f"[SKIP] {input_path} (Already distilled)")
                return

            start_time = time.perf_counter()
            
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Metadata for context
            metadata = {
                "source": str(input_path),
                "title": input_path.stem
            }
            
            # Perform distillation
            distilled_content = await distiller.distill(content, metadata)
            
            if not distilled_content or len(distilled_content.strip()) < 50:
                print(f"[WARN] Distillation result too short or empty for {input_path}. Skipping save.")
                return

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save distilled content
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(distilled_content)
                
            duration = time.perf_counter() - start_time
            print(f"[SUCCESS] Distilled {input_path} -> {output_path} ({duration:.2f}s)")
            
        except Exception as e:
            print(f"[ERROR] Failed to process {input_path}: {e}")

async def main():
    parser = argparse.ArgumentParser(description="PRTS Knowledge Distillation Orchestrator")
    parser.add_argument("--input-dir", type=str, default="docs/prts", help="Raw markdown directory")
    parser.add_argument("--output-dir", type=str, default="docs/prts_distilled", help="Distilled markdown directory")
    parser.add_argument("--concurrency", type=int, default=8, help="LLM call concurrency (default: 8)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of files to process (for testing)")
    args = parser.parse_args()

    distiller = KnowledgeDistiller()
    input_base = Path(args.input_dir)
    output_base = Path(args.output_dir)
    
    if not input_base.exists():
        print(f"[ERROR] Input directory {args.input_dir} does not exist.")
        return

    # Find all markdown files
    md_files = sorted(list(input_base.glob("**/*.md")))
    
    # Filter out files that are already up to date to get an accurate count of work to do
    files_to_process = []
    for md_file in md_files:
        rel_path = md_file.relative_to(input_base)
        dest_path = output_base / rel_path
        if not dest_path.exists() or dest_path.stat().st_mtime < md_file.stat().st_mtime:
            files_to_process.append(md_file)
            
    if args.limit > 0:
        files_to_process = files_to_process[:args.limit]
        
    print(f"[INFO] Found {len(md_files)} total files.")
    print(f"[INFO] Files needing distillation: {len(files_to_process)}")
    
    if not files_to_process:
        print("[INFO] Everything is up to date.")
        return

    print(f"[INFO] Starting distillation with concurrency={args.concurrency}...")
    start_total = time.perf_counter()

    semaphore = asyncio.Semaphore(args.concurrency)
    tasks = []
    
    for md_file in files_to_process:
        # Calculate relative path to maintain structure
        rel_path = md_file.relative_to(input_base)
        dest_path = output_base / rel_path
        tasks.append(process_file(distiller, md_file, dest_path, semaphore))
    
    await asyncio.gather(*tasks)
    
    total_duration = time.perf_counter() - start_total
    print(f"\n[DONE] Distillation complete.")
    print(f"[INFO] Total time: {total_duration:.2f}s")
    print(f"[INFO] Results saved to: {args.output_dir}")

if __name__ == "__main__":
    asyncio.run(main())

