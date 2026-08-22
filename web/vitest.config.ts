import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * The one thing the defaults lack: the `@/` alias tsconfig and Next both understand, which
 * the components under test import through. Everything else stays default -- a node
 * environment, with the two DOM tests opting into jsdom by docblock.
 */
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
});
