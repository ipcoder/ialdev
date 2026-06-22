import * as esbuild from 'esbuild';
import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const outFile = resolve(root, '../src/iad/vis/imview/static/imgrid.js');
mkdirSync(dirname(outFile), { recursive: true });

const watch = process.argv.includes('--watch');

const ctx = await esbuild.context({
  entryPoints: [resolve(root, 'src/index.ts')],
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: ['es2020'],
  outfile: outFile,
  minify: !watch,
  sourcemap: watch,
});

if (watch) {
  await ctx.watch();
  console.log('watching imview bundle...');
} else {
  await ctx.rebuild();
  await ctx.dispose();
  console.log('built', outFile);
}
