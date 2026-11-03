#!/usr/bin/env bash
# master.sh IN.mp4 OUT.mp4 [I=-14] [TP=-1]  - two-pass loudnorm of the audio, picture copied untouched.
set -e
IN="$1"; OUT="$2"; I="${3:--14}"; TP="${4:--1}"
J=$(ffmpeg -nostdin -hide_banner -i "$IN" -vn -af "loudnorm=I=$I:TP=$TP:LRA=11:print_format=json" -f null - 2>&1 | sed -n '/^{/,/^}/p')
g(){ echo "$J" | sed -n "s/.*\"$1\" : \"\([^\"]*\)\".*/\1/p"; }
ffmpeg -nostdin -v error -y -i "$IN" -c:v copy -af "loudnorm=I=$I:TP=$TP:LRA=11:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true,aresample=48000,alimiter=limit=0.83:level=disabled:attack=1:release=60" \
  -c:a aac -b:a 256k -ar 48000 -movflags +faststart "$OUT"
ffmpeg -nostdin -hide_banner -i "$OUT" -vn -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I:|Peak:|LRA:)" | tr -s ' '
