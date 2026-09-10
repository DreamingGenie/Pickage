'use strict';

// One process per bridge, with candidate state confined to one target package.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const readline = require('node:readline');
const { createRequire } = require('node:module');
const semverRoot = process.argv[2];
const argumentRoot = process.argv[3];
if (!semverRoot || !argumentRoot) throw new Error('Explicit npm module paths are required');
const semver = require(semverRoot);
const npa = require(argumentRoot);
const options = { loose: false, includePrerelease: false };
let packageName = null;
let validPackageName = false;
let candidates = [];
let candidateSet = new Set();
let sorted = false;

function moduleFingerprint(root) {
  const entries = [];
  function walk(directory) {
    for (const item of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0)) {
      if (item.isSymbolicLink()) throw new Error('Module symlinks are not supported');
      const file = path.join(directory, item.name);
      if (item.isDirectory()) walk(file);
      else if (/\.(?:js|cjs|json)$/.test(item.name)) {
        entries.push([path.relative(root, file).split(path.sep).join('/'), crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')]);
      }
    }
  }
  walk(root);
  return crypto.createHash('sha256').update(JSON.stringify(entries)).digest('hex');
}

// Resolve the installed dependency closure, including hoisted npm modules.
// Hash logical package identities and content, never host-specific paths.
function dependencyFingerprint(roots) {
  const visited = new Set();
  const records = [];
  function visit(root) {
    root = fs.realpathSync(root);
    if (visited.has(root)) return;
    visited.add(root);
    const manifestPath = path.join(root, 'package.json');
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
    records.push([manifest.name, manifest.version, moduleFingerprint(root)]);
    const localRequire = createRequire(manifestPath);
    for (const name of Object.keys(manifest.dependencies || {}).sort()) {
      let directory = path.dirname(localRequire.resolve(name));
      while (true) {
        const candidate = path.join(directory, 'package.json');
        if (fs.existsSync(candidate) && JSON.parse(fs.readFileSync(candidate, 'utf8')).name === name) break;
        const parent = path.dirname(directory);
        if (parent === directory) throw new Error('Cannot identify installed resolver dependency');
        directory = parent;
      }
      visit(directory);
    }
  }
  roots.forEach(visit);
  records.sort((a, b) => JSON.stringify(a) < JSON.stringify(b) ? -1 : JSON.stringify(a) > JSON.stringify(b) ? 1 : 0);
  return crypto.createHash('sha256').update(JSON.stringify(records)).digest('hex');
}

const metadata = {
  node_version: process.version,
  semver_version: require(path.join(semverRoot, 'package.json')).version,
  package_arg_version: require(path.join(argumentRoot, 'package.json')).version,
  semver_sha256: moduleFingerprint(semverRoot),
  package_arg_sha256: moduleFingerprint(argumentRoot),
  dependency_closure_sha256: dependencyFingerprint([semverRoot, argumentRoot]),
  options,
  equal_precedence_tie: 'original_version_utf16_ascending',
};

function resolve(requirement) {
  const result = { requirement, status: null, normalized_range: null, target_version: null };
  if (!validPackageName) { result.status = 'INVALID_PACKAGE_NAME'; return result; }
  if (typeof requirement !== 'string' || requirement.includes('\u0000')) {
    result.status = 'INVALID_SPEC';
    return result;
  }
  let parsed;
  try { parsed = npa.resolve(packageName, requirement); }
  catch (_) { result.status = 'INVALID_SPEC'; return result; }
  const unsupported = { alias: 'UNSUPPORTED_ALIAS', tag: 'UNSUPPORTED_TAG', git: 'UNSUPPORTED_GIT',
    file: 'UNSUPPORTED_FILE', directory: 'UNSUPPORTED_FILE', remote: 'UNSUPPORTED_URL' };
  if (unsupported[parsed.type]) { result.status = unsupported[parsed.type]; return result; }
  if (!['range', 'version'].includes(parsed.type)) { result.status = 'INVALID_SPEC'; return result; }
  result.normalized_range = semver.validRange(parsed.fetchSpec, options);
  if (result.normalized_range === null) { result.status = 'INVALID_SPEC'; return result; }
  // maxSatisfying preserves the first equal-precedence candidate. Sorting the
  // original strings supplies a reproducible tie policy without using ordinal.
  if (!sorted) { candidates.sort(); sorted = true; }
  result.target_version = semver.maxSatisfying(candidates, parsed.fetchSpec, options);
  result.status = result.target_version !== null ? 'RESOLVED'
    : candidates.length ? 'NO_SATISFYING_VERSION' : 'NO_ELIGIBLE_TARGET';
  return result;
}

function handle(message) {
  if (message.op === 'metadata') return metadata;
  if (message.op === 'start') {
    if (typeof message.name !== 'string' || !message.name || message.name.includes('\u0000')) {
      throw new Error('Target package name must be a nonempty string');
    }
    packageName = message.name;
    try { npa.resolve(packageName, '*'); validPackageName = true; }
    catch (_) { validPackageName = false; }
    candidates = [];
    candidateSet = new Set();
    sorted = false;
    return { started: true };
  }
  if (packageName === null) throw new Error('Start a target package first');
  if (message.op === 'candidates') {
    if (!Array.isArray(message.versions)) throw new Error('Candidate batch must be an array');
    const rejected = [];
    for (const version of message.versions) {
      const valid = typeof version === 'string' ? semver.valid(version, options) : null;
      if (valid === null) rejected.push({ version, reason: 'INVALID_TARGET_SEMVER' });
      else if (semver.prerelease(valid) !== null) rejected.push({ version, reason: 'PRERELEASE_TARGET' });
      else if (!candidateSet.has(version)) { candidateSet.add(version); candidates.push(version); sorted = false; }
    }
    return { accepted_total: candidates.length, rejected };
  }
  if (message.op === 'resolve') {
    if (!Array.isArray(message.requirements)) throw new Error('Requirement batch must be an array');
    return message.requirements.map(resolve);
  }
  throw new Error('Unknown bridge operation');
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on('line', line => {
  try { process.stdout.write(JSON.stringify({ ok: true, result: handle(JSON.parse(line)) }) + '\n'); }
  catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, error: error.message }) + '\n');
    process.exitCode = 1;
    lines.close();
  }
});
