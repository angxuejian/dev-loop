import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig([
  {
    files: ["{backend,frontend,scripts,features}/**/*.js"],
    extends: [js.configs.recommended],
  },
  {
    files: ["{backend,frontend,scripts,features}/**/*.ts"],
    extends: [tseslint.configs.recommended],
  },
]);
