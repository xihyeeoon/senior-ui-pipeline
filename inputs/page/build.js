/* Renders DesignRepair's example .tsx into a static page for Playwright.
   Usage: node build.js [example1.tsx]
   Precompiles JSX with esbuild (in-browser Babel fails on this file). */
const fs = require('fs');
const { execFileSync } = require('child_process');

const name = process.argv[2] || 'example1.tsx';
const src = fs.readFileSync(`../../vendor/designrepair/examples/${name}`, 'utf8')
  .replace(/^export default function Component/m, 'function Component');

fs.writeFileSync('_src.tsx',
  src + '\nReactDOM.createRoot(document.getElementById("root")).render(<Component />);\n');

execFileSync('npx', ['--yes', 'esbuild@0.25.0', '_src.tsx',
  '--jsx=transform', '--format=iife', '--outfile=app.js'],
  { stdio: 'inherit', shell: true });

fs.writeFileSync('index.html', `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DesignRepair ${name}</title>
<script src="https://cdn.tailwindcss.com"></script>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
</head><body>
<div id="root"></div>
<script src="./app.js"></script>
</body></html>
`);
console.log(`built ${name} -> index.html + app.js`);
