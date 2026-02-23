#!/usr/bin/env node

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {fileURLToPath} from "node:url";

const SKILL_NAME = "news-aggregator-skill";
const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE_ITEMS = ["SKILL.md", "templates.md", "requirements.txt", "scripts", "README.md"];

function printHelp() {
  console.log(`news-aggregator-skill CLI

Usage:
  news-aggregator-skill install [--target claude|opencode|cursor|both|all] [--dir <absolute-path>] [--dry-run]
  news-aggregator-skill --help

Options:
  --target   Install target (default: both)
  --dir      Custom target directory (overrides --target)
  --dry-run  Show actions without writing files

Examples:
  npx @stevegogogo/news-aggregator-skill install
  npx @stevegogogo/news-aggregator-skill install --target claude
  npx @stevegogogo/news-aggregator-skill install --target opencode
  npx @stevegogogo/news-aggregator-skill install --target cursor
  npx @stevegogogo/news-aggregator-skill install --target all
  npx @stevegogogo/news-aggregator-skill install --dir ~/.claude/skills/news-aggregator-skill
`);
}

function parseArgs(argv) {
  const args = {
    command: null,
    target: "both",
    customDir: "",
    dryRun: false,
    help: false,
  };

  const items = [...argv];
  if (items.length === 0) {
    args.help = true;
    return args;
  }

  if (items[0] === "--help" || items[0] === "-h") {
    args.help = true;
    return args;
  }

  args.command = items.shift();

  while (items.length > 0) {
    const token = items.shift();
    if (token === "--help" || token === "-h") {
      args.help = true;
      continue;
    }
    if (token === "--dry-run") {
      args.dryRun = true;
      continue;
    }
    if (token === "--target") {
      const next = items.shift();
      if (!next || !["claude", "opencode", "cursor", "both", "all"].includes(next)) {
        throw new Error("--target must be one of: claude, opencode, cursor, both, all");
      }
      args.target = next;
      continue;
    }
    if (token === "--dir") {
      const next = items.shift();
      if (!next) {
        throw new Error("--dir requires a path value");
      }
      args.customDir = next;
      continue;
    }
    throw new Error(`Unknown argument: ${token}`);
  }

  return args;
}

function resolveInstallTargets(target, customDir) {
  if (customDir) {
    return [path.resolve(customDir.replace(/^~(?=$|\/|\\)/, os.homedir()))];
  }

  const homeDir = os.homedir();
  const map = {
    claude: [path.join(homeDir, ".claude", "skills", SKILL_NAME)],
    opencode: [path.join(homeDir, ".config", "opencode", "skills", SKILL_NAME)],
    cursor: [path.join(homeDir, ".cursor", "skills", SKILL_NAME)],
    both: [
      path.join(homeDir, ".claude", "skills", SKILL_NAME),
      path.join(homeDir, ".config", "opencode", "skills", SKILL_NAME),
    ],
    all: [
      path.join(homeDir, ".claude", "skills", SKILL_NAME),
      path.join(homeDir, ".config", "opencode", "skills", SKILL_NAME),
      path.join(homeDir, ".cursor", "skills", SKILL_NAME),
    ],
  };
  return map[target] || map.both;
}

function copySkill(targetDir, dryRun) {
  console.log(`\n[install] ${targetDir}`);
  if (dryRun) {
    for (const item of SOURCE_ITEMS) {
      console.log(`  - copy ${item}`);
    }
    return;
  }

  fs.mkdirSync(path.dirname(targetDir), {recursive: true});
  fs.rmSync(targetDir, {recursive: true, force: true});
  fs.mkdirSync(targetDir, {recursive: true});

  for (const item of SOURCE_ITEMS) {
    const src = path.join(ROOT_DIR, item);
    const dest = path.join(targetDir, item);
    const stat = fs.statSync(src);
    if (stat.isDirectory()) {
      fs.cpSync(src, dest, {recursive: true});
    } else {
      fs.copyFileSync(src, dest);
    }
    console.log(`  - copied ${item}`);
  }
}

function printNextSteps(targets, dryRun) {
  if (dryRun) {
    console.log("\n[dry-run] No files were written.");
    return;
  }
  console.log("\nInstall complete.");
  for (const dir of targets) {
    console.log(`- ${dir}`);
    console.log(`  Next: pip install -r \"${path.join(dir, "requirements.txt")}\"`);
  }
  console.log("\nUsage tip:");
  console.log(`- In Claude/OpenCode chat, say: \"${SKILL_NAME} 如意如意\"`);
}

function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(`[error] ${error.message}`);
    printHelp();
    process.exit(1);
  }

  if (args.help || !args.command) {
    printHelp();
    return;
  }

  if (args.command !== "install") {
    console.error(`[error] Unsupported command: ${args.command}`);
    printHelp();
    process.exit(1);
  }

  const targets = resolveInstallTargets(args.target, args.customDir);
  for (const targetDir of targets) {
    copySkill(targetDir, args.dryRun);
  }
  printNextSteps(targets, args.dryRun);
}

main();
