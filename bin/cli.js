#!/usr/bin/env node
'use strict';

// Installs the document-anything skill into an agent's skills folder and runs its Python scripts.
// No dependencies: Node >= 16 and Python >= 3.9.

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const SKILL_NAME = 'document-anything';
const PACKAGE_ROOT = path.resolve(__dirname, '..');
const SKILL_SRC = path.join(PACKAGE_ROOT, 'skill');
const MARKER = '.document-anything-install.json';
const VERSION = require(path.join(PACKAGE_ROOT, 'package.json')).version;

const HELP = `document-anything ${VERSION}

Usage:
  document-anything install [--project] [--dir <skills-root>] [--force]
      Copies the skill to ~/.claude/skills/${SKILL_NAME} (default), to ./.claude/skills/${SKILL_NAME}
      with --project, or to <skills-root>/${SKILL_NAME} with --dir (other agents, e.g. ~/.codex/skills).
  document-anything uninstall [--project] [--dir <skills-root>]
  document-anything where [--project] [--dir <skills-root>]   Prints the install path.
  document-anything doctor                                   Checks Python and the bundled scripts.

  document-anything types                                    Lists the document types.
  document-anything blueprint <type> [--lang en]             Prints the sections of a type.
  document-anything new --type <t> --title <t> --subject <s> -o <doc.md>   Writes a skeleton.
  document-anything scan <repo>... [--format json]           Suggested type + fact inventory of a codebase.
  document-anything validate <doc.md> [--repo <repo>...]     Gate for a document pair (exit 1 on errors).
  document-anything render <doc.md> [--check]                Renders (or checks) the HTML page.
`;

function fail(message) {
  console.error(`document-anything: ${message}`);
  process.exit(1);
}

function parseFlags(args) {
  const flags = { project: false, force: false, dir: null };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--project') flags.project = true;
    else if (args[i] === '--force') flags.force = true;
    else if (args[i] === '--dir') flags.dir = args[++i] || fail('--dir needs a path');
    else fail(`unknown option ${args[i]}`);
  }
  return flags;
}

function targetDir(flags) {
  if (flags.dir) return path.resolve(flags.dir.replace(/^~(?=$|[\\/])/, os.homedir()), SKILL_NAME);
  const base = flags.project ? process.cwd() : os.homedir();
  return path.join(base, '.claude', 'skills', SKILL_NAME);
}

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    if (entry.name === '__pycache__' || entry.name.endsWith('.pyc')) continue;
    const from = path.join(src, entry.name);
    const to = path.join(dst, entry.name);
    if (entry.isDirectory()) copyDir(from, to);
    else fs.copyFileSync(from, to);
  }
}

function ownedByUs(dir) {
  return fs.existsSync(path.join(dir, MARKER));
}

function install(flags) {
  const dst = targetDir(flags);
  if (fs.existsSync(dst)) {
    if (!ownedByUs(dst) && !flags.force) {
      fail(`${dst} exists and was not installed by this package; re-run with --force to replace it`);
    }
    fs.rmSync(dst, { recursive: true, force: true });
  }
  copyDir(SKILL_SRC, dst);
  fs.writeFileSync(path.join(dst, MARKER), JSON.stringify({ version: VERSION, installedAt: new Date().toISOString() }, null, 2) + '\n');
  console.log(`Installed ${SKILL_NAME} ${VERSION} at ${dst}`);
  const py = findPython();
  if (!py) console.log('Warning: Python >= 3.9 was not found; the skill needs it for its validators.');
  console.log('Restart the agent session to load the skill, then ask: "document this" / "documente isto".');
}

function uninstall(flags) {
  const dst = targetDir(flags);
  if (!fs.existsSync(dst)) return console.log(`Nothing to remove at ${dst}`);
  if (!ownedByUs(dst)) fail(`${dst} was not installed by this package; remove it by hand if intended`);
  fs.rmSync(dst, { recursive: true, force: true });
  console.log(`Removed ${dst}`);
}

function findPython() {
  const candidates = process.platform === 'win32'
    ? [['python'], ['py', '-3'], ['python3']]
    : [['python3'], ['python']];
  for (const [cmd, ...pre] of candidates) {
    const res = spawnSync(cmd, [...pre, '--version'], { encoding: 'utf8' });
    const m = /Python (\d+)\.(\d+)/.exec(`${res.stdout || ''}${res.stderr || ''}`);
    if (res.status === 0 && m && (Number(m[1]) > 3 || (Number(m[1]) === 3 && Number(m[2]) >= 9))) {
      return { cmd, pre, version: `${m[1]}.${m[2]}` };
    }
  }
  return null;
}

function runScript(script, args) {
  const py = findPython() || fail('Python >= 3.9 not found (tried python3, python, py -3)');
  const res = spawnSync(py.cmd, [...py.pre, path.join(SKILL_SRC, 'scripts', script), ...args], { stdio: 'inherit' });
  process.exit(res.status === null ? 1 : res.status);
}

function doctor() {
  const py = findPython();
  console.log(`package    ${VERSION} (${PACKAGE_ROOT})`);
  console.log(`node       ${process.version}`);
  console.log(`python     ${py ? `${py.version} (${[py.cmd, ...py.pre].join(' ')})` : 'NOT FOUND (need >= 3.9)'}`);
  for (const flags of [{}, { project: true }]) {
    const dst = targetDir(flags);
    console.log(`${flags.project ? 'project' : 'user'}    ${fs.existsSync(dst) ? 'installed' : 'not installed'} at ${dst}`);
  }
  if (!py) process.exit(1);
  for (const script of ['scan_repo.py', 'new_doc.py', 'validate_wiki.py', 'render_wiki.py']) {
    const res = spawnSync(py.cmd, [...py.pre, path.join(SKILL_SRC, 'scripts', script), '--help'], { encoding: 'utf8' });
    console.log(`${script.padEnd(17)}${res.status === 0 ? 'ok' : `FAILED\n${res.stderr}`}`);
    if (res.status !== 0) process.exit(1);
  }
}

const [command, ...rest] = process.argv.slice(2);
switch (command) {
  case 'install': install(parseFlags(rest)); break;
  case 'uninstall': uninstall(parseFlags(rest)); break;
  case 'where': console.log(targetDir(parseFlags(rest))); break;
  case 'doctor': doctor(); break;
  case 'types': runScript('new_doc.py', ['--list']); break;
  case 'blueprint': runScript('new_doc.py', ['--print', ...rest]); break;
  case 'new': runScript('new_doc.py', rest); break;
  case 'scan': runScript('scan_repo.py', rest); break;
  case 'validate': runScript('validate_wiki.py', rest); break;
  case 'render': runScript('render_wiki.py', rest); break;
  case undefined: case 'help': case '--help': case '-h': console.log(HELP); break;
  case '--version': case '-v': console.log(VERSION); break;
  default: fail(`unknown command ${command}\n\n${HELP}`);
}
