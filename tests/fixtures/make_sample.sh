#!/usr/bin/env bash
set -euo pipefail
output="${1:-data/sample.mp4}"
mkdir -p "$(dirname "$output")"
ffmpeg -hide_banner -loglevel error -nostdin -n \
  -f lavfi -i 'color=c=0x16352e:s=1920x1080:r=30:d=10' \
  -f lavfi -i 'color=c=0xefbe75:s=160x160:r=30:d=10' \
  -filter_complex "[0:v][1:v]overlay=x='880+180*sin(t*0.6)':y='460+80*sin(t*0.4)':shortest=1[v]" \
  -map '[v]' -an -c:v libx264 -preset ultrafast -crf 20 -pix_fmt yuv420p \
  -threads 1 -filter_complex_threads 1 -fflags +bitexact -flags:v +bitexact \
  -map_metadata -1 -t 10 "$output"
