#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { lstat, readFile, readdir, realpath, writeFile } from 'node:fs/promises';
import path from 'node:path';

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Parametro richiesto: ${name}`);
  return process.argv[index + 1];
}

const packageDir = await realpath(argument('--package'));
const inventoryFile = path.resolve(argument('--inventory'));
const releaseSha = argument('--release-sha');
if (!/^[a-f0-9]{40}$/i.test(releaseSha)) throw new Error('Release SHA non valido.');

const allowedRoots = [
  'themes/sarafatto',
  'plugins/sarafatto-core',
  'mu-plugins/sarafatto-polylang-front-page-url.php',
];
const requiredEntries = [
  'assets/src/js/app.js',
  'assets/src/js/home.js',
  'assets/src/js/product.js',
  'assets/src/js/product-archive.js',
];
const distDir = path.join(packageDir, 'themes/sarafatto/assets/dist');
const manifestPath = path.join(distDir, '.vite/manifest.json');
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));

function safeRelative(value) {
  if (typeof value !== 'string' || !value || value.includes('\\') || value.startsWith('/')) {
    throw new Error(`Percorso manifest non valido: ${String(value)}`);
  }
  const normalized = path.posix.normalize(value);
  if (normalized === '..' || normalized.startsWith('../')) throw new Error(`Path traversal nel manifest: ${value}`);
  return normalized;
}

async function requireAsset(relative, context) {
  const safe = safeRelative(relative);
  const target = path.resolve(distDir, safe);
  if (!target.startsWith(`${path.resolve(distDir)}${path.sep}`)) {
    throw new Error(`Riferimento fuori dalla build: ${relative} (${context})`);
  }
  const info = await lstat(target);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`Asset assente o non regolare: ${relative} (${context})`);
}

for (const key of requiredEntries) {
  if (!manifest[key]?.isEntry || !manifest[key]?.file) throw new Error(`Entry Vite mancante/incompleto: ${key}`);
}

for (const [key, entry] of Object.entries(manifest)) {
  if (!entry || typeof entry !== 'object') throw new Error(`Voce manifest non valida: ${key}`);
  if (entry.file) await requireAsset(entry.file, key);
  for (const asset of [...(entry.css ?? []), ...(entry.assets ?? [])]) await requireAsset(asset, key);
  for (const imported of [...(entry.imports ?? []), ...(entry.dynamicImports ?? [])]) {
    if (!Object.hasOwn(manifest, imported)) throw new Error(`Import manifest inesistente: ${key} -> ${imported}`);
  }
}

const files = [];
async function walk(directory) {
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, item.name);
    const relative = path.relative(packageDir, full).split(path.sep).join('/');
    if (/[\t\r\n]/.test(relative)) throw new Error(`Nome file non rappresentabile nell'inventario: ${relative}`);
    const info = await lstat(full);
    if (info.isSymbolicLink()) throw new Error(`Symlink vietato nell'artefatto: ${relative}`);
    if (info.isDirectory()) await walk(full);
    else if (info.isFile()) files.push({ relative, full, size: info.size });
    else throw new Error(`Tipo file non supportato: ${relative}`);
  }
}

for (const root of allowedRoots) {
  const full = path.join(packageDir, ...root.split('/'));
  const info = await lstat(full).catch(() => null);
  if (!info || info.isSymbolicLink()) throw new Error(`Percorso di rilascio mancante o symlink: ${root}`);
  if (info.isDirectory()) await walk(full);
  else if (info.isFile()) files.push({ relative: root, full, size: info.size });
  else throw new Error(`Tipo di percorso non supportato: ${root}`);
}

const inventory = [];
for (const file of files.sort((a, b) => a.relative.localeCompare(b.relative))) {
  const digest = createHash('sha256').update(await readFile(file.full)).digest('hex');
  inventory.push(`${digest}\t${file.size}\t${file.relative}`);
}
await writeFile(inventoryFile, `${inventory.join('\n')}\n`, { flag: 'w' });
console.log(`Manifest valido: 4 entrypoint; ${files.length} file inclusi; SHA ${releaseSha}.`);
