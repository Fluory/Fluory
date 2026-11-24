# Vendored libraries

Everything the page needs is served from this repository – no CDN, no third-party requests.

| File | Package | Version | Licence |
|---|---|---|---|
| `three.min.js` | [three](https://www.npmjs.com/package/three) | 0.186.0 | MIT – `LICENSE-three.txt` |
| `gsap.min.js` | [gsap](https://www.npmjs.com/package/gsap) (`dist/gsap.min.js`, unchanged) | 3.15.1 | GSAP Standard "No Charge" License – `LICENSE-gsap.txt` |
| `ScrollTrigger.min.js` | [gsap](https://www.npmjs.com/package/gsap) (`dist/ScrollTrigger.min.js`, unchanged) | 3.15.1 | GSAP Standard "No Charge" License – `LICENSE-gsap.txt` |

`three.min.js` is a minified ES module containing only the classes the page uses
(tree-shaken, licence header kept). Rebuild it with:

```sh
npm i three@0.186.0 esbuild@0.25.10
echo "export { WebGLRenderer, Scene, OrthographicCamera, BufferGeometry, BufferAttribute, ShaderMaterial, Points, Color } from 'three';" > three-entry.js
npx esbuild three-entry.js --bundle --format=esm --minify --legal-comments=inline --target=es2020 --outfile=three.min.js
```

## Fonts (`../fonts/`)

| File | Package | Version | Licence |
|---|---|---|---|
| `instrument-sans-wght.woff2` | @fontsource-variable/instrument-sans (`latin-wght-normal`) | 5.3.0 | SIL OFL 1.1 – `LICENSE-InstrumentSans.txt` |
| `instrument-serif-italic.woff2` | @fontsource/instrument-serif (`latin-400-italic`) | 5.3.0 | SIL OFL 1.1 – `LICENSE-InstrumentSerif.txt` |
| `jetbrains-mono-wght.woff2` | @fontsource-variable/jetbrains-mono (`latin-wght-normal`) | 5.3.0 | SIL OFL 1.1 – `LICENSE-JetBrainsMono.txt` |

The README graphics (`../../assets/*.svg`) embed small subsets of the same fonts (OFL allows this).
