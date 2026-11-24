#!/bin/bash
for i in $(seq 1 60); do
  if grep -q REBUILD_DONE /opt/ai-workbench/rebuild.log 2>/dev/null; then
    echo FOUND_DONE
    tail -n 40 /opt/ai-workbench/rebuild.log
    exit 0
  fi
  if ! pgrep -f remote-rebuild.sh >/dev/null && ! pgrep -f 'compose build' >/dev/null; then
    echo PROCESS_ENDED
    tail -n 60 /opt/ai-workbench/rebuild.log
    exit 1
  fi
  echo WAIT_$i
  sleep 15
done
echo TIMEOUT
tail -n 40 /opt/ai-workbench/rebuild.log
exit 2
