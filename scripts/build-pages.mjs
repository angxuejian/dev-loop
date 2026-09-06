import { access, copyFile, mkdir, readdir, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repositoryRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const typescriptBin = join(
  repositoryRoot,
  "node_modules",
  "typescript",
  "bin",
  "tsc",
);

function isDevelopmentFile(name) {
  return (
    (name.startsWith(".") && name !== ".build") ||
    name === ".gitignore" ||
    /^README(?:\..+)?$/i.test(name) ||
    /^package(?:-lock)?\.json$/i.test(name) ||
    /^tsconfig(?:\..+)?\.json$/i.test(name) ||
    /\.(?:ts|tsx|map)$/i.test(name) ||
    /\.(?:test|spec)\.[^.]+$/i.test(name)
  );
}

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function copyStaticFiles(source, destination) {
  await mkdir(destination, { recursive: true });
  for (const entry of await readdir(source, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) {
      throw new Error(
        `Pages source must not contain symbolic links: ${join(source, entry.name)}`,
      );
    }
    if (isDevelopmentFile(entry.name)) continue;

    const sourcePath = join(source, entry.name);
    const destinationPath = join(destination, entry.name);
    if (entry.isDirectory()) {
      await copyStaticFiles(sourcePath, destinationPath);
    } else if (entry.isFile()) {
      await copyFile(sourcePath, destinationPath);
    }
  }
}

function compileApp(appDirectory) {
  const config = join(appDirectory, "tsconfig.json");
  const result = spawnSync(
    process.execPath,
    [typescriptBin, "--project", config],
    {
      cwd: repositoryRoot,
      stdio: "inherit",
    },
  );
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(
      `TypeScript build failed for ${relative(repositoryRoot, appDirectory)}`,
    );
  }
}

export async function buildPages({
  frontendRoot = join(repositoryRoot, "frontend"),
  outputRoot = join(repositoryRoot, "pages-dist"),
  compile = true,
} = {}) {
  const applications = [];
  for (const entry of await readdir(frontendRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const directory = join(frontendRoot, entry.name);
    if (await exists(join(directory, "index.html"))) {
      applications.push({ name: entry.name, directory });
    }
  }
  if (applications.length === 0) {
    throw new Error("No frontend applications with an index.html were found");
  }
  applications.sort((first, second) => first.name.localeCompare(second.name));

  await rm(outputRoot, { recursive: true, force: true });
  await mkdir(outputRoot, { recursive: true });
  for (const application of applications) {
    if (
      compile &&
      (await exists(join(application.directory, "tsconfig.json")))
    ) {
      compileApp(application.directory);
    }
    await copyStaticFiles(
      application.directory,
      join(outputRoot, application.name),
    );
  }
  return applications.map(({ name }) => name);
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  buildPages()
    .then((applications) =>
      console.log(`Prepared Pages applications: ${applications.join(", ")}`),
    )
    .catch((error) => {
      console.error(error instanceof Error ? error.message : error);
      process.exitCode = 1;
    });
}
