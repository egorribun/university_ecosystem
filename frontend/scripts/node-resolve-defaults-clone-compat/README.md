# Node-resolve fixed-defaults clone adapter

First-party, private compatibility code for the single fixed-defaults clone in official @rollup/plugin-node-resolve 16.0.3. This is not deepmerge, a fork of it, or a general merging API. It accepts only an empty ordinary target and the exact seven-field literal defaults of that consumer, then uses Node structuredClone. All changed shapes, options, accessor properties and unsupported calls fail closed. The consumer retains its original deepFreeze operation.

The root npm override is limited to exact node-resolve16.0.3. The installed import edge named deepmerge intentionally resolves to this truthfully named scoped package. The shim exists because deepmerge 4.3.1 is affected by GHSA-gcqx-w48m-w2h4 (low, prototype poisoning in mergeObject(), as reported by npm audit for deepmerge 4.3.1). No deepmerge engine is copied; this adapter has no external dependencies or lifecycle scripts. Changing the consumer version or defaults requires a new source review and tests.

Upstream provenance: https://github.com/rollup/plugins/tree/node-resolve-v16.0.3/packages/node-resolve . Review its official integrity-checked distribution and retained registry lock integrity. A file link has no tarball integrity: source provenance is the reviewed repository commit and source manifest, and local code requires review beyond npm audit.

Run the companion node-resolve-defaults-clone-compat.test.mjs in hosted CI, plus real Workbox/VitePWA build, resolution and offline behavior acceptance. A lower audit count alone is not correctness evidence.
