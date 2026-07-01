#!/bin/sh
# Add a 2G swapfile on this 4GB/no-swap box. Without swap, reading the 4.2G MongoDB during
# a dump fills page cache, the kernel goes into direct reclaim (kswapd0 pegs a core), mongo
# stops responding (mongodump "i/o timeout"), and sshd starves. A little swap + low
# swappiness lets the kernel spill cold pages instead of thrashing.
set -eu

if sudo swapon --show=NAME --noheadings | grep -q '/swapfile'; then
  echo "swapfile already active"; sudo swapon --show; exit 0
fi

echo "creating /swapfile (2G)"
sudo fallocate -l 2G /swapfile 2>/dev/null || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
sudo chmod 600 /swapfile
sudo mkswap /swapfile >/dev/null
sudo swapon /swapfile

grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null

# Prefer reclaiming page cache; only swap under real pressure.
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-etelemetry-swap.conf >/dev/null
sudo sysctl -q vm.swappiness=10

echo "done:"; sudo swapon --show; free -m | head -2
