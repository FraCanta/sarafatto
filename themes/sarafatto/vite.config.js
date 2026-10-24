import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { writeFile, rm } from 'node:fs/promises';

const root = dirname(fileURLToPath(import.meta.url));
const hotFile = resolve(root, 'hot');

function wordpressHotFile() {
  return {
    name: 'sarafatto-wordpress-hot-file',
    async configureServer(server) {
      await writeFile(hotFile, server.config.server.origin || 'http://localhost:5173');
      server.httpServer?.once('close', () => rm(hotFile, { force: true }));
    },
  };
}

export default defineConfig({
  root,
  base: process.env.NODE_ENV === 'development' ? '/' : './',
  plugins: [wordpressHotFile()],
  server: { host: '0.0.0.0', port: 5173, strictPort: true, cors: true },
  build: {
    outDir: 'assets/dist',
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        app: resolve(root, 'assets/src/js/app.js'),
        home: resolve(root, 'assets/src/js/home.js'),
        product: resolve(root, 'assets/src/js/product.js'),
        productArchive: resolve(root, 'assets/src/js/product-archive.js'),
      },
    },
  },
});
