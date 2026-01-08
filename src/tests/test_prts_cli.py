#!/usr/bin/env python3
"""
Test script for PRTS DB CLI
Tests the basic functionality without full integration
"""

import os
import sys

def test_imports():
    """Test if all required imports work"""
    print("[TEST] Testing imports...")
    try:
        from src.cli.chroma_query_tool import ChromaQueryTool
        print("  ✓ ChromaQueryTool import successful")
        
        import chromadb
        print("  ✓ chromadb import successful")
        
        from src.config import get_global_embeddings
        print("  ✓ get_global_embeddings import successful")
        
        from src.config.llm_config import create_chroma_client
        print("  ✓ create_chroma_client import successful")
        
        return True
    except Exception as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_cli_structure():
    """Test if the CLI script is valid Python"""
    print("\n[TEST] Testing CLI structure...")
    try:
        with open('src/cli/prts_db_cli.py', 'r') as f:
            code = f.read()
        
        # Basic syntax check
        compile(code, 'src/cli/prts_db_cli.py', 'exec')
        print("  ✓ CLI syntax valid")
        
        # Check for required classes
        if 'class PRTSDBManager' in code:
            print("  ✓ PRTSDBManager class found")
        else:
            print("  ✗ PRTSDBManager class not found")
            return False
        
        # Check for required methods
        required_methods = ['query_menu', 'ingest_menu', 'distill_menu', 'delete_menu']
        for method in required_methods:
            if f'def {method}' in code:
                print(f"  ✓ {method} method found")
            else:
                print(f"  ✗ {method} method not found")
                return False
        
        return True
    except Exception as e:
        print(f"  ✗ Structure test failed: {e}")
        return False


def test_ingest_modifications():
    """Test if ingest_md.py has the required modifications"""
    print("\n[TEST] Testing ingest_md.py modifications...")
    try:
        with open('src/data/ingestion/ingest_md.py', 'r') as f:
            code = f.read()
        
        # Check for is_distilled parameter
        if 'is_distilled: bool | None = None' in code:
            print("  ✓ is_distilled parameter added to ingest_markdown")
        else:
            print("  ✗ is_distilled parameter not found")
            return False
        
        # Check for --is-distilled argument
        if '--is-distilled' in code:
            print("  ✓ --is-distilled CLI argument added")
        else:
            print("  ✗ --is-distilled CLI argument not found")
            return False
        
        # Check for auto-detection logic
        if "'distilled' in docs_dir.lower()" in code:
            print("  ✓ Auto-detection logic present")
        else:
            print("  ✗ Auto-detection logic not found")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Ingest modifications test failed: {e}")
        return False


def test_file_existence():
    """Test if all required files exist"""
    print("\n[TEST] Testing file existence...")
    
    required_files = [
        'src/cli/prts_db_cli.py',
        'src/cli/chroma_query_tool.py',
        'src/data/ingestion/ingest_md.py',
        'src/data/distillation/distill_knowledge.py',
        'src/cli/db_manager.py'
    ]
    
    all_exist = True
    for file in required_files:
        if os.path.exists(file):
            print(f"  ✓ {file} exists")
        else:
            print(f"  ✗ {file} not found")
            all_exist = False
    
    return all_exist


def main():
    print("="*60)
    print("PRTS DB CLI Test Suite")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("File Existence", test_file_existence()))
    results.append(("Imports", test_imports()))
    results.append(("CLI Structure", test_cli_structure()))
    results.append(("Ingest Modifications", test_ingest_modifications()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! The CLI is ready to use.")
        return 0
    else:
        print("\n❌ Some tests failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
