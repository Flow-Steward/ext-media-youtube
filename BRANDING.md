# Branding

`icon.png` is the YouTube icon (the red rounded rectangle with the white play triangle), the
full-color version YouTube publishes for third parties, used only to identify this integration
in Flow Steward.

## Source

- Product: YouTube, a service of Google LLC — <https://www.youtube.com/>.
- Official asset: the YouTube brand resources site, page **YouTube Icon**
  (<https://brand.youtube/youtube-icon>, reached from
  <https://www.youtube.com/howyoutubeworks/resources/brand-resources/>), download
  <https://www.gstatic.com/marketing-cms/78/29/3e68a1414bb28d0b7e47b44c3c91/youtube-icon.zip>,
  downloaded 2026-11-23.
- SHA-256 of `youtube-icon.zip`: `ca9b5104387e0f7afcfda3a79c910449561112f1077177dd0d64f8c72f56e476`.
- File used from the archive: `YouTube_Icon/Digital/01 Red/yt_icon_red_digital.png`
  (1255 × 1075, RGBA), SHA-256 `1027b1b0517727adb9697155a270744381c3ce9b047b1c8bd8a9389dc7d07a83`.

## What was done

- The empty transparent margin around the icon was trimmed (the icon itself is 827 × 579), the
  icon was scaled proportionally to 180 × 126 px and centered on a transparent 256 × 256
  canvas (ImageMagick: `-trim -resize 180x -gravity center -extent 256x256`). Colors, shape and
  proportions are unchanged. The icon is 126 px tall, above the 100 px digital minimum of the
  brand page, with 38 px of empty space left and right and 65 px above and below.
- SHA-256 of `icon.png`: `fb322da575201bf9b0873aaee8dac7f0eaea922e46d5ba61c453dc3c74cb3223`.

## Use

YouTube and the YouTube logo are trademarks of Google LLC. The icon is used unaltered in form
and color, only to show which service this integration connects to; it does not imply
endorsement by Google or YouTube. The brand page's rules were followed: full-color icon with
a white triangle, no stroke, shadow, rotation, stretching or custom colors, and a digital height
of at least 100 px.
