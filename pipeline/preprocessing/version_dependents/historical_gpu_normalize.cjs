'use strict';

// Experimental stable-only rank adapter. The production worker stays unchanged.
const readline = require('node:readline');
const path = require('node:path');
const semver = require(process.argv[2]);
const npa = require(process.argv[3]);
const options = { loose: false, includePrerelease: false };
const MAX_FRAME = 7 * 1024 * 1024;

function parse(name, requirement) {
  const result = { requirement, normalized_range: null, fixed_status: null, spans: [] };
  let validName = typeof name === 'string' && !!name && !name.includes('\u0000');
  if (validName) { try { npa.resolve(name, '*'); } catch (_) { validName = false; } }
  if (!validName) return { ...result, fixed_status: 'INVALID_PACKAGE_NAME' };
  if (typeof requirement !== 'string' || requirement.includes('\u0000'))
    return { ...result, fixed_status: 'INVALID_SPEC' };
  let parsed;
  try { parsed = npa.resolve(name, requirement); }
  catch (_) { return { ...result, fixed_status: 'INVALID_SPEC' }; }
  const unsupported = { alias: 'UNSUPPORTED_ALIAS', tag: 'UNSUPPORTED_TAG', git: 'UNSUPPORTED_GIT',
    file: 'UNSUPPORTED_FILE', directory: 'UNSUPPORTED_FILE', remote: 'UNSUPPORTED_URL' };
  if (unsupported[parsed.type]) return { ...result, fixed_status: unsupported[parsed.type] };
  if (!['range', 'version'].includes(parsed.type)) return { ...result, fixed_status: 'INVALID_SPEC' };
  result.normalized_range = semver.validRange(parsed.fetchSpec, options);
  if (result.normalized_range === null) return { ...result, fixed_status: 'INVALID_SPEC' };
  try { result.range = new semver.Range(parsed.fetchSpec, options); }
  catch (_) { result.fixed_status = 'INVALID_SPEC'; }
  return result;
}

function boundary(candidates, value, strict) {
  let lo = 0, hi = candidates.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2);
    const order = semver.compare(candidates[mid].valid, value);
    if (order < 0 || (strict && order === 0)) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function spansFor(range, candidates) {
  const spans = [];
  for (const set of range.set) {
    let lo = 0, hi = candidates.length;
    for (const comparator of set) {
      if (comparator.value === '') continue; // ANY comparator.
      const value = comparator.semver;
      switch (comparator.operator) {
        case '>': lo = Math.max(lo, boundary(candidates, value, true)); break;
        case '>=': lo = Math.max(lo, boundary(candidates, value, false)); break;
        case '<': hi = Math.min(hi, boundary(candidates, value, false)); break;
        case '<=': hi = Math.min(hi, boundary(candidates, value, true)); break;
        case '':
          lo = Math.max(lo, boundary(candidates, value, false));
          hi = Math.min(hi, boundary(candidates, value, true)); break;
        default: throw new Error('Unexpected comparator operator');
      }
    }
    if (lo < hi) spans.push([lo, hi]);
  }
  spans.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged = [];
  for (const span of spans) {
    const prior = merged[merged.length - 1];
    if (prior && span[0] <= prior[1]) prior[1] = Math.max(prior[1], span[1]);
    else merged.push(span.slice());
  }
  return merged;
}

function normalize(message) {
  if (message.op !== 'package') throw new Error('Only package operation is supported');
  if (!Number.isInteger(message.snapshot_count) || message.snapshot_count < 1 || message.snapshot_count > 4096)
    throw new Error('Invalid snapshot_count');
  if (typeof message.known_package !== 'boolean') throw new Error('known_package must be boolean');
  if (!Array.isArray(message.candidates) || message.candidates.length > 100000)
    throw new Error('Invalid candidates');
  if (!message.known_package && message.candidates.length) throw new Error('Unmapped package cannot have candidates');
  if (!Array.isArray(message.requirements) || message.requirements.length > 2048 ||
      new Set(message.requirements).size !== message.requirements.length ||
      message.requirements.some(r => typeof r !== 'string' && r !== null))
    throw new Error('Invalid or duplicate requirements');
  const started = performance.now();
  const seen = new Map(), accepted = [], rejected = [], ranked = [];
  for (const candidate of message.candidates) {
    if (!candidate || typeof candidate !== 'object' || !Number.isInteger(candidate.birth_index) ||
        candidate.birth_index < 0 || candidate.birth_index >= message.snapshot_count)
      throw new Error('Invalid candidate birth_index');
    const key = typeof candidate.version === 'string' ? candidate.version : JSON.stringify(candidate.version);
    if (seen.has(key)) {
      if (seen.get(key) !== candidate.birth_index) throw new Error('Duplicate candidate has conflicting birth_index');
      continue;
    }
    seen.set(key, candidate.birth_index);
    const valid = typeof candidate.version === 'string' ? semver.valid(candidate.version, options) : null;
    if (valid === null) rejected.push({ ...candidate, reason: 'INVALID_TARGET_SEMVER' });
    else if (semver.prerelease(valid) !== null) rejected.push({ ...candidate, reason: 'PRERELEASE_TARGET' });
    else {
      accepted.push({ version: candidate.version, birth_index: candidate.birth_index });
      ranked.push({ version: candidate.version, birth_index: candidate.birth_index, valid });
    }
  }
  ranked.sort((a, b) => semver.compare(a.valid, b.valid) ||
    (a.version < b.version ? 1 : a.version > b.version ? -1 : 0));
  const candidatesDone = performance.now();
  const lookups = message.requirements.map(requirement => {
    const item = parse(message.name, requirement);
    if (!item.fixed_status) item.spans = spansFor(item.range, ranked);
    return item;
  });
  const normalizedDone = performance.now();
  let comparisons = 0;
  if (message.verify_spans === true) {
    for (const item of lookups) {
      if (item.fixed_status) continue;
      let spanIndex = 0;
      for (let rank = 0; rank < ranked.length; rank++) {
        while (spanIndex < item.spans.length && item.spans[spanIndex][1] <= rank) spanIndex++;
        const inside = spanIndex < item.spans.length && item.spans[spanIndex][0] <= rank;
        if (inside !== item.range.test(ranked[rank].valid)) throw new Error('Rank spans differ from npm Range.test');
        comparisons++;
      }
    }
  }
  for (const item of lookups) delete item.range;
  return { snapshot_count: message.snapshot_count, known_package: message.known_package,
    rank_to_version: ranked.map(c => c.version), birth_by_rank: ranked.map(c => c.birth_index),
    earliest_accepted_birth: ranked.reduce((v, c) => Math.min(v, c.birth_index), message.snapshot_count),
    accepted, rejected, lookups,
    runtime: { node: process.version, semver: require(path.join(process.argv[2], 'package.json')).version,
      package_arg: require(path.join(process.argv[3], 'package.json')).version, options,
      tie: 'original_version_utf16_ascending', candidates: 'stable_only' },
    metrics: { candidate_normalization_seconds: (candidatesDone - started) / 1000,
      range_normalization_seconds: (normalizedDone - candidatesDone) / 1000,
      span_verification_seconds: (performance.now() - normalizedDone) / 1000,
      span_membership_comparisons: comparisons } };
}

const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on('line', line => {
  try {
    if (Buffer.byteLength(line, 'utf8') > MAX_FRAME) throw new Error('Request exceeds framing bound');
    const result = normalize(JSON.parse(line));
    const response = JSON.stringify({ ok: true, result }) + '\n';
    if (Buffer.byteLength(response, 'utf8') > MAX_FRAME) throw new Error('Response exceeds framing bound');
    process.stdout.write(response);
  } catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, error: error.message }) + '\n');
    process.exitCode = 1;
    lines.close();
  }
});
