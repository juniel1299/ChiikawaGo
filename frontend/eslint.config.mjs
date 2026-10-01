import { defineConfig, globalIgnores } from "eslint/config";
import js from "@eslint/js";
import next from "@next/eslint-plugin-next";
import ts from "typescript-eslint";
import globals from "globals";

export default defineConfig([
  js.configs.recommended,
  ...ts.configs.recommended,
  next.configs["core-web-vitals"],
  { languageOptions: { globals: { ...globals.browser, ...globals.node } } },
  globalIgnores([".next/**", "next-env.d.ts", "playwright-report/**", "test-results/**"]),
]);
