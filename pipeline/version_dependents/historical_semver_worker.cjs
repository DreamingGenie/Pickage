'use strict';

// Bounded date-aware resolver for H3.  It intentionally has no state shared
// with the legacy worker: one request contains one target package and the
// candidate birth index at which each version becomes eligible.
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const semverRoot = process.argv[2];
const argumentRoot = process.argv[3];
if (!semverRoot || !argumentRoot) throw new Error('Explicit npm module paths are required');
const semver = require(semverRoot);
const npa = require(argumentRoot);
const options = { loose: false, includePrerelease: false };
const MAX_SNAPSHOTS = 4096;
const MAX_CANDIDATES = 100000;
const MAX_REQUIREMENTS = 512;
const MAX_WORK = 2000000;
const MAX_INTERVALS = 20000;
const MAX_FRAME_BYTES = 7 * 1024 * 1024;

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
  interval_end: 'exclusive',
  bounds: { max_snapshots: MAX_SNAPSHOTS, max_candidates: MAX_CANDIDATES,
    max_unique_requirements: MAX_REQUIREMENTS, max_candidate_requirement_work: MAX_WORK,
    max_result_intervals: MAX_INTERVALS, max_frame_bytes: MAX_FRAME_BYTES },
};

function fail(message) { throw new Error(message); }

function validateRequest(message) {
  if (!message || message.op !== 'package') fail('Only package operation is supported');
  if (!Number.isInteger(message.snapshot_count) || message.snapshot_count < 1 || message.snapshot_count > MAX_SNAPSHOTS)
    fail(`snapshot_count must be an integer between 1 and ${MAX_SNAPSHOTS}`);
  if (!Array.isArray(message.candidates) || message.candidates.length > MAX_CANDIDATES)
    fail(`candidates must be an array of at most ${MAX_CANDIDATES}`);
  if (!Array.isArray(message.requirements) || message.requirements.length > MAX_REQUIREMENTS)
    fail(`requirements must be an array of at most ${MAX_REQUIREMENTS}`);
  if (message.candidates.length * Math.max(message.requirements.length, 1) > MAX_WORK)
    fail(`candidate_requirement_work exceeds ${MAX_WORK}`);
  if (typeof message.known_package !== 'boolean') fail('known_package must be boolean');
  if (!message.known_package && message.candidates.length) fail('Unmapped package cannot have candidate versions');
  for (const candidate of message.candidates) {
    if (!candidate || typeof candidate !== 'object' || !Number.isInteger(candidate.birth_index) ||
        candidate.birth_index < 0 || candidate.birth_index >= message.snapshot_count)
      fail('candidate birth_index is outside snapshot bounds');
  }
  for (const requirement of message.requirements)
    if (typeof requirement !== 'string' && requirement !== null) fail('requirements must contain strings or null');
  if (new Set(message.requirements).size !== message.requirements.length) fail('requirements must be unique');
}

function validPackageName(name) {
  if (typeof name !== 'string' || !name || name.includes('\u0000')) return false;
  try { npa.resolve(name, '*'); return true; } catch (_) { return false; }
}

function parseRequirement(name, requirement) {
  const result = { requirement, normalized_range: null, parsed: null, fixed_status: null };
  if (!validPackageName(name)) { result.fixed_status = 'INVALID_PACKAGE_NAME'; return result; }
  if (typeof requirement !== 'string' || requirement.includes('\u0000')) {
    result.fixed_status = 'INVALID_SPEC'; return result;
  }
  let parsed;
  try { parsed = npa.resolve(name, requirement); } catch (_) {
    result.fixed_status = 'INVALID_SPEC'; return result;
  }
  const unsupported = { alias: 'UNSUPPORTED_ALIAS', tag: 'UNSUPPORTED_TAG', git: 'UNSUPPORTED_GIT',
    file: 'UNSUPPORTED_FILE', directory: 'UNSUPPORTED_FILE', remote: 'UNSUPPORTED_URL' };
  if (unsupported[parsed.type]) { result.fixed_status = unsupported[parsed.type]; return result; }
  if (!['range', 'version'].includes(parsed.type)) { result.fixed_status = 'INVALID_SPEC'; return result; }
  result.normalized_range = semver.validRange(parsed.fetchSpec, options);
  if (result.normalized_range === null) { result.fixed_status = 'INVALID_SPEC'; return result; }
  try { result.parsed = new semver.Range(parsed.fetchSpec, options); } catch (_) { result.fixed_status = 'INVALID_SPEC'; }
  return result;
}

function resolveIntervals(message, parsed, batches) {
  const intervals = [];
  let candidateChecks = 0;
  const add = (start, end, status, normalized_range, target_version) => {
    if (end <= start) return;
    const prior = intervals[intervals.length - 1];
    if (prior && prior.end_index === start && prior.status === status &&
        prior.normalized_range === normalized_range && prior.target_version === target_version) {
      prior.end_index = end;
    } else intervals.push({ start_index: start, end_index: end, status,
      normalized_range, target_version });
  };
  if (parsed.fixed_status) {
    add(0, message.snapshot_count, parsed.fixed_status, null, null);
    return { intervals, candidateChecks };
  }
  let winner = null;
  let activeCount = 0;
  let start = 0;
  let status = message.known_package ? 'NO_ELIGIBLE_TARGET' : 'UNMAPPED_TARGET_PACKAGE';
  for (const [index, candidates] of batches) {
    const previousVersion = winner ? winner.version : null;
    const previousStatus = status;
    activeCount += candidates.length;
    for (const candidate of candidates) {
      candidateChecks += 1;
      if (!parsed.parsed.test(candidate.valid)) continue;
      const order = winner ? semver.compare(candidate.valid, winner.valid) : 1;
      if (order > 0 || (order === 0 && candidate.version < winner.version)) winner = candidate;
    }
    status = winner ? 'RESOLVED' : (activeCount ? 'NO_SATISFYING_VERSION' : previousStatus);
    if (status !== previousStatus || (winner ? winner.version : null) !== previousVersion) {
      add(start, index, previousStatus, parsed.normalized_range, previousVersion);
      start = index;
    }
  }
  add(start, message.snapshot_count, status, parsed.normalized_range, winner ? winner.version : null);
  return { intervals, candidateChecks };
}

function handle(message) {
  if (message.op === 'metadata') return metadata;
  validateRequest(message);
  const name = message.name;
  const seen = new Map();
  const accepted = [];
  const rejected = [];
  const byBirth = new Map();
  for (const candidate of message.candidates) {
    const key = typeof candidate.version === 'string' ? candidate.version : JSON.stringify(candidate.version);
    if (seen.has(key)) {
      if (seen.get(key) !== candidate.birth_index) fail('Duplicate candidate has conflicting birth_index');
      continue;
    }
    seen.set(key, candidate.birth_index);
    const valid = typeof candidate.version === 'string' ? semver.valid(candidate.version, options) : null;
    if (valid === null) rejected.push({ version: candidate.version, birth_index: candidate.birth_index, reason: 'INVALID_TARGET_SEMVER' });
    else if (semver.prerelease(valid) !== null) rejected.push({ version: candidate.version, birth_index: candidate.birth_index, reason: 'PRERELEASE_TARGET' });
    else {
      if (!byBirth.has(candidate.birth_index)) byBirth.set(candidate.birth_index, []);
      byBirth.get(candidate.birth_index).push({ version: candidate.version, valid });
      accepted.push({ version: candidate.version, birth_index: candidate.birth_index });
    }
  }
  const batches = [...byBirth.entries()].sort((a, b) => a[0] - b[0]);
  const requirements = message.requirements.map(requirement => parseRequirement(name, requirement));
  let candidateChecks = 0;
  let intervalCount = 0;
  const lookups = requirements.map((parsed, index) => {
    const resolved = resolveIntervals(message, parsed, batches);
    intervalCount += resolved.intervals.length;
    if (intervalCount > MAX_INTERVALS) fail('Result interval bound exceeded; use smaller requirement batches');
    candidateChecks += resolved.candidateChecks;
    return { requirement: message.requirements[index], intervals: resolved.intervals };
  });
  return { lookups, accepted, rejected, metrics: {
    candidate_checks: candidateChecks,
    parsed_requirements: requirements.filter(item => item.parsed !== null).length,
  }};
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on('line', line => {
  try {
    if (Buffer.byteLength(line, 'utf8') > MAX_FRAME_BYTES) fail('Request exceeds framing bound');
    const response = JSON.stringify({ ok: true, result: handle(JSON.parse(line)) }) + '\n';
    if (Buffer.byteLength(response, 'utf8') > MAX_FRAME_BYTES) fail('Response exceeds framing bound');
    process.stdout.write(response);
  }
  catch (error) { process.stdout.write(JSON.stringify({ ok: false, error: error.message }) + '\n'); process.exitCode = 1; lines.close(); }
});
