/* Builds a side-by-side comparison of the three example1 variants.
   Each variant is a standalone page rendered in its own iframe at a fixed
   logical width, so Tailwind's md:/lg:/xl: breakpoints behave as they do in
   the real 1280px render that Playwright saw.
   Sources live here in tools/compare/; every generated file goes to
   outputs/compare/, which is git-ignored.
   Usage: node tools/compare/build.js */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const SRC_ROOT = path.join(__dirname, '..', '..');
const OUT = path.join(SRC_ROOT, 'outputs', 'compare');
fs.mkdirSync(OUT, { recursive: true });

const VARIANTS = [
  { id: 'orig',   label: 'Original',        sub: 'examples/example1.tsx',
    src: path.join(SRC_ROOT, 'vendor/designrepair/examples/example1.tsx') },
  { id: 'base',   label: 'Base KB',         sub: 'system_design_knowledge_base.csv - 12 suggestions, 0 rule IDs',
    src: path.join(SRC_ROOT, 'outputs/example1_base/property_example1.tsx') },
  { id: 'senior', label: 'Senior KB',       sub: 'senior_kb.csv - 17 suggestions, 12 SDF-* citations',
    src: path.join(SRC_ROOT, 'outputs/example1_seniorkb/property_example1.tsx') },
];

const HEAD = `<script src="https://cdn.tailwindcss.com"></script>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>`;

for (const v of VARIANTS) {
  const src = fs.readFileSync(v.src, 'utf8')
    .replace(/^export default function Component/m, 'function Component');
  fs.writeFileSync(path.join(OUT, `_${v.id}.tsx`),
    src + `\nReactDOM.createRoot(document.getElementById("root")).render(<Component />);\n`);
  execFileSync('npx', ['--yes', 'esbuild@0.25.0', path.join(OUT, `_${v.id}.tsx`),
    '--jsx=transform', '--format=iife', `--outfile=${path.join(OUT, v.id + '.js')}`],
    { stdio: 'inherit', shell: true });
  fs.writeFileSync(path.join(OUT, `${v.id}.html`), `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${v.label}</title>
${HEAD}
</head><body style="margin:0">
<div id="root"></div>
<script src="./${v.id}.js"></script>
</body></html>
`);
  console.log(`built ${v.id} <- ${v.src}`);
}
fs.writeFileSync(path.join(OUT, 'variants.json'), JSON.stringify(VARIANTS.map(({id,label,sub}) => ({id,label,sub})), null, 2));
