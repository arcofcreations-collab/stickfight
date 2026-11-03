#!/usr/bin/env bash
# mix_sfx.sh IN.mp4 STEM.wav OUT.mp4 [stem_dB=-9] [fade_out_s=0]
# Lays the SFX stem under the song already in IN.mp4: the stem is high-passed and carved out of the vocal
# presence band so the voice stays on top, then the whole mix goes through master.sh (-14 LUFS, <= -1 dBTP).
set -e
IN="$1"; STEM="$2"; OUT="$3"; G="${4:--9}"; FO="${5:-0}"
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$IN")
FADE=""
if [ "$FO" != "0" ]; then FADE=",afade=t=out:st=$(awk "BEGIN{print $DUR - $FO}"):d=$FO"; fi
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="${OUT%.mp4}_premix.mkv"
ffmpeg -nostdin -v error -y -i "$IN" -i "$STEM" -filter_complex \
 "[1:a]highpass=f=70,equalizer=f=2600:width_type=o:width=1.4:g=-4,equalizer=f=1200:width_type=o:width=1:g=-2,volume=${G}dB[s];[0:a]aresample=48000[m];[m][s]amix=inputs=2:normalize=0:duration=first${FADE}[a]" \
 -map 0:v -map "[a]" -c:v copy -c:a pcm_s16le "$TMP"
bash "$HERE/master.sh" "$TMP" "$OUT"
rm -f "$TMP"
