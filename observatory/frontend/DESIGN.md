# Visual implementation brief
The user explicitly requests a procedural Three.js universe. The scene is rendered from real coordinates; decorative stars/nebula remain independent of data. No image assets or network fonts are required.

- Background #070b12, panel #0d131d, raised #141e2a, borders #253040.
- Text #e7edf4; muted #8f9daf; mint accent #77e1c6, blue secondary #86a6ed.
- Fonts: system sans, SFMono-Regular/Consolas for numbers and metadata.
- Desktop: 64px top bar, 76px metric strip, 244px left tree, flexible view, 300px inspector; bottom 250px object table under center view. On narrow screens tree/inspector become explicit tabs above stacked scene/table.
- Clear compact app chrome, uppercase ASTRA brand only, no promotional hero, charts or invented stats.
- Lucide outline icons 16px, 1.5px stroke; shared button/input states and 8px baseline spacing.
- Scene: restrained violet/blue procedural haze, stars behind true colored points, orbit/pan/zoom, selected mint ring, explicit same-frame annotation and sample count.
- All metrics from API; defaults shown as dash before connection. Empty state gives ingest path and start instructions.
- UI reads a stable list snapshot. Metrics update every 3s; additions prompt explicit refresh. Selection and scroll remain untouched.
