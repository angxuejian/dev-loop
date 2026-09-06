import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { buildPages } from "../../scripts/build-pages.mjs";

test("packages every direct frontend application and excludes development files", async (context) => {
  const fixture = await mkdtemp(join(tmpdir(), "dev-loop-pages-"));
  context.after(() => rm(fixture, { recursive: true, force: true }));
  const frontend = join(fixture, "frontend");
  const output = join(fixture, "pages-dist");

  await mkdir(join(frontend, "card-draw", ".build"), { recursive: true });
  await mkdir(join(frontend, "xxa", "assets"), { recursive: true });
  await mkdir(join(frontend, "not-an-app", "nested"), { recursive: true });
  await Promise.all([
    writeFile(join(frontend, "card-draw", "index.html"), "card draw"),
    writeFile(join(frontend, "card-draw", ".build", "main.js"), "compiled"),
    writeFile(join(frontend, "card-draw", "main.ts"), "source"),
    writeFile(join(frontend, "card-draw", "draw.test.mjs"), "test"),
    writeFile(join(frontend, "card-draw", "README.md"), "docs"),
    writeFile(join(frontend, "card-draw", ".env"), "secret"),
    writeFile(join(frontend, "card-draw", "package.json"), "{}"),
    writeFile(join(frontend, "card-draw", "tsconfig.json"), "{}"),
    writeFile(join(frontend, "xxa", "index.html"), "xxa"),
    writeFile(join(frontend, "xxa", "assets", "site.css"), "style"),
    writeFile(join(frontend, "not-an-app", "nested", "index.html"), "nested"),
  ]);

  assert.deepEqual(
    await buildPages({
      frontendRoot: frontend,
      outputRoot: output,
      compile: false,
    }),
    ["card-draw", "xxa"],
  );
  assert.equal(
    await readFile(join(output, "card-draw", "index.html"), "utf8"),
    "card draw",
  );
  assert.equal(
    await readFile(join(output, "card-draw", ".build", "main.js"), "utf8"),
    "compiled",
  );
  assert.equal(
    await readFile(join(output, "xxa", "assets", "site.css"), "utf8"),
    "style",
  );

  for (const excluded of [
    "main.ts",
    "draw.test.mjs",
    "README.md",
    ".env",
    "package.json",
    "tsconfig.json",
  ]) {
    await assert.rejects(readFile(join(output, "card-draw", excluded)));
  }
  await assert.rejects(
    readFile(join(output, "not-an-app", "nested", "index.html")),
  );
});
