# MPL source access for JavaScript dependency-path components

The frontend production dependency graph contains Lightning CSS 1.33.0,
including optional native bindings. Additional development/tooling paths use
1.32.0. These are tooling/SSR dependency paths, not evidence that each native
binary is delivered to a browser. Their MPL-2.0 license text is retained in
`frontend-runtime-js-notices.txt` or `linux-optional-toolchain-notices.txt`.
The following source revisions are taken from the exact official npm version
metadata (`gitHead`); the archives provide upstream source form. No local
modifications to these upstream packages are recorded by this audit.

- Lightning CSS 1.33.0: [version-bound source tree](https://github.com/parcel-bundler/lightningcss/tree/1d680fa14e9a089c92dc0929f869d6757ae91c30), [source archive](https://github.com/parcel-bundler/lightningcss/archive/1d680fa14e9a089c92dc0929f869d6757ae91c30.tar.gz).
- Lightning CSS 1.32.0: [version-bound source tree](https://github.com/parcel-bundler/lightningcss/tree/7f8a861bdee476fe90c89a8badeb3fd33a99c51a), [source archive](https://github.com/parcel-bundler/lightningcss/archive/7f8a861bdee476fe90c89a8badeb3fd33a99c51a.tar.gz).

The source archives retain their Cargo lockfiles and upstream notices; preserve
any additional native/transitive dependency source obligations in an actual
binary distribution. The aggregate JavaScript inventory is not a full rebuild
or audit of every optional native binding's contents.

DOMPurify 3.4.17 offers `MPL-2.0 OR Apache-2.0`; it can be used under the offered
Apache-2.0 alternative. Both original package notices are preserved in the
JavaScript bundle. A license choice for that package does not change MPL-only
components' obligations. The other component licenses and any prior project
permissions continue to apply independently of the project's new terms.
