#!/usr/bin/env python3
"""
Main entry point for comprehensive testing
Runs all tests in parallel and combines results
"""
import subprocess
import multiprocessing
from pathlib import Path
import json
import time
from comprehensive_test_framework import ComprehensiveTester
import yaml

def run_test_suite(rom_path: Path, output_base: Path):
    """Run comprehensive test suite"""
    output_base.mkdir(parents=True, exist_ok=True)
    
    # Load expected mapping
    monster_map_path = Path("palettes/monster_palette_map.yaml")
    expected_mapping = {}
    if monster_map_path.exists():
        with open(monster_map_path) as f:
            expected_mapping = yaml.safe_load(f)
    
    print("🧪 Starting comprehensive test suite...")
    print(f"   ROM: {rom_path}")
    print(f"   Output: {output_base}")
    print()
    
    # Create tester
    tester = ComprehensiveTester(rom_path, output_base)
    
    # Run mgba-headless test
    print("1️⃣  Running mgba-headless test...")
    test_result = tester.run_mgba_headless_test(duration_seconds=5)
    
    if not test_result.get("success"):
        print(f"   ❌ Failed: {test_result.get('error', 'Unknown')}")
        return False
    
    print("   ✅ mgba-headless test completed")
    print()
    
    # Analyze results
    print("2️⃣  Analyzing results...")
    
    # Performance
    perf = tester.analyze_performance()
    if "error" not in perf:
        print(f"   Performance: {perf['average_fps']:.1f} FPS avg")
    
    # Screenshots
    screenshots = tester.analyze_screenshots()
    if "error" not in screenshots:
        print(f"   Screenshots: {screenshots['total_screenshots']} captured")
    
    # OAM
    oam = tester.analyze_oam_logs()
    if "error" not in oam:
        print(f"   OAM writes: {oam['total_oam_writes']} logged")
    
    # Comparison
    comparison = tester.compare_with_expected(expected_mapping)
    if "error" not in comparison:
        print(f"   Accuracy: {comparison['accuracy']*100:.1f}% ({comparison['matches']}/{comparison['matches']+comparison['mismatches']+comparison['missing']})")
    
    print()
    
    # Generate report
    print("3️⃣  Generating report...")
    report = tester.generate_report(expected_mapping)
    print(report)
    
    # Save summary JSON
    summary = {
        "timestamp": time.time(),
        "rom": str(rom_path),
        "performance": perf if "error" not in perf else None,
        "screenshots": screenshots if "error" not in screenshots else None,
        "oam": oam if "error" not in oam else None,
        "comparison": comparison if "error" not in comparison else None
    }
    
    summary_file = output_base / "summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"   ✅ Report saved to: {output_base / 'analysis' / 'test_report.txt'}")
    print(f"   ✅ Summary saved to: {summary_file}")
    
    return True

def main():
    import sys
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    output_dir = Path("test_output") / f"test_{int(time.time())}"
    
    if len(sys.argv) > 1:
        rom_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        sys.exit(1)
    
    success = run_test_suite(rom_path, output_dir)
    
    if success:
        print("\n✅ Test suite completed successfully!")
        print(f"📊 View results in: {output_dir}")
    else:
        print("\n❌ Test suite failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

