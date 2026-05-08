#!/bin/bash
cd /home/struktured/projects/penta-dragon-dx-claude/rl
echo "=== Training Status (`date`) ==="
echo
echo "v6 (entropy=0.03):"
grep "Chunk done" logs/shalamar_v6_chunked.log 2>/dev/null | tail -3
echo
echo "explore (entropy=0.10):"
grep "Chunk done" logs/shalamar_explore_chunked.log 2>/dev/null | tail -3
echo
echo "Recent epochs:"
grep -E "^ep " logs/shalamar_v6_chunked.log 2>/dev/null | tail -3
echo
echo "Total advances (kills):"
echo "  v6: $(grep -c "FFBA ADVANCE" logs/shalamar_v6_chunked.log 2>/dev/null)"
echo "  explore: $(grep -c "FFBA ADVANCE" logs/shalamar_explore_chunked.log 2>/dev/null)"
echo
echo "Active processes:"
ps -ef | grep -E "train_loop|train_shalamar" | grep -v grep | wc -l
