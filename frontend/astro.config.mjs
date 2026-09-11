// @ts-check
import { defineConfig } from 'astro/config';
import { loadEnv } from 'vite';

import tailwindcss from '@tailwindcss/vite';

const mode = process.env.NODE_ENV === 'production' ? 'production' : 'development';
const env = loadEnv(mode, process.cwd(), '');
const apiUrl = (process.env.PUBLIC_API_URL ?? env.PUBLIC_API_URL)?.replace(/\/+$/, '');

// https://astro.build/config
export default defineConfig({
  vite: {
    plugins: [tailwindcss()],
    server: {
      proxy: apiUrl ? {
        '/api': {
          target: apiUrl,
          changeOrigin: true,
        },
      } : undefined,
    },
  },
});
