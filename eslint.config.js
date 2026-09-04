import js from "@eslint/js";
import { defineConfig } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig([
  {
    files: ["src/**/*.js"],
    extends: [js.configs.recommended],
  },
  {
    files: ["src/**/*.ts"],
    extends: [tseslint.configs.recommended],
  },
]);
