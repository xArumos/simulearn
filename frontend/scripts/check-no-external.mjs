#!/usr/bin/env node
// Fails if the built app (frontend/dist) could make a request to another host.
//
// - index.html: no src/href pointing at http(s):// or // URLs.
// - CSS: no url(...) or @import pointing at another host (fonts are self-hosted).
// - JS: every absolute URL in the bundle must be on the allowlist below. These
//   are strings libraries carry (XML namespaces, links inside error messages,
//   a URL base for parsing) and are never fetched.
//
// Usage: node scripts/check-no-external.mjs [distDir]
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const dist = process.argv[2] ?? new URL("../dist", import.meta.url).pathname;

const ALLOWED_PREFIXES = [
  "http://www.w3.org/", // SVG / XHTML / MathML namespace identifiers
  "https://react.dev/errors/", // React's minified-error help link (text only)
  "https://reactrouter.com/", // React Router docs links in warnings (text only)
  "https://tailwindcss.com", // licence banner comment in the CSS
  "http://localhost", // base URL React Router uses to parse relative paths
];

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const problems = [];
const files = walk(dist);
const textFiles = files.filter((f) => /\.(html|css|js|mjs|svg|json|txt)$/.test(f));

for (const file of textFiles) {
  const rel = relative(dist, file);
  const text = readFileSync(file, "utf8");

  if (file.endsWith(".html")) {
    for (const m of text.matchAll(/\b(?:src|href|action|poster)\s*=\s*["']?\s*((?:https?:)?\/\/[^"'\s>]+)/gi)) {
      problems.push(`${rel}: external reference ${m[1]}`);
    }
  }
  if (file.endsWith(".css") || file.endsWith(".html")) {
    for (const m of text.matchAll(/url\(\s*["']?((?:https?:)?\/\/[^"')\s]+)/gi)) {
      problems.push(`${rel}: external url() ${m[1]}`);
    }
    for (const m of text.matchAll(/@import\s+(?:url\()?\s*["']?((?:https?:)?\/\/[^"')\s;]+)/gi)) {
      problems.push(`${rel}: external @import ${m[1]}`);
    }
  }
  for (const m of text.matchAll(/https?:\/\/[^\s"'`)<>\\]+/g)) {
    if (!ALLOWED_PREFIXES.some((p) => m[0].startsWith(p))) {
      problems.push(`${rel}: unexpected absolute URL ${m[0]}`);
    }
  }
}

if (problems.length) {
  console.error(`check-no-external: ${problems.length} problem(s) in ${dist}`);
  for (const p of [...new Set(problems)]) console.error("  " + p);
  process.exit(1);
}
console.log(`check-no-external: OK (${textFiles.length} text files, ${files.length} files in ${relative(process.cwd(), dist) || dist})`);
