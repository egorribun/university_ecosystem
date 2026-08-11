window.BENCHMARK_DATA = {
  "lastUpdate": 1786469013981,
  "repoUrl": "https://github.com/egorribun/university_ecosystem",
  "entries": {
    "WS-Hub Regression Gate": [
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "496ed7f2c5c0fd33da738b4687b4c31281f14d7e",
          "message": "fix(ci): restore checks after draft pull requests become ready (#1227)\n\n* feat(wave212): remove obsolete handoff prompt\n\n* fix(ci): trigger checks when draft PR becomes ready\n\n* test(quality): cover gateway TLS certificate failure paths\n\n* fix(ci): keep required OpenAPI check live on every PR\n\n* fix(ci): run frontend mutation gate during manual recovery\n\n* test(gateway): satisfy Go lint and nil analysis\n\n* fix(ci): add manual recovery triggers for Go analysis\n\n* fix(ci): make gosec test directive effective\n\n* fix(ci): use canonical lighthouse assertions\n\n* fix(ci): eliminate ws-hub shutdown race\n\n* fix(ci): handle ws-hub socket cleanup error\n\n* fix(ci): reduce ws-hub server complexity\n\n* fix(ci): align lighthouse gates with canonical config\n\n* fix(ci): isolate backend integration test scope\n\n* fix(ci): start minio for chaos services\n\n* fix(quality): consume frontend statement coverage\n\n* fix(ci): close PR check and coverage gaps\n\n* fix(ci): close analyzer findings\n\n* fix(ci): drain file processor servers before return\n\n* fix(ci): close coverage gate deficits\n\n* fix(ci): make PR quality gate reproducible\n\n* fix(ci): prevent security scan alert drift\n\n* fix(ci): retry testcontainer image pulls\n\n* fix(ci): stabilize browser e2e execution\n\n* fix(ci): close mutation and tier0 coverage gaps\n\n* fix(ci): unblock code scanning ruleset\n\n* fix(ci): preserve scoped trivy suppressions\n\n* fix(ci): filter suppressed checkov alerts\n\n* fix(ci): write filtered checkov sarif separately\n\n* fix(ci): use one trivy ignore format\n\n* fix(ci): make Semgrep SARIF analysis reliable\n\n* fix(ci): make Semgrep pull requests diff-aware\n\n* fix(ci): close Semgrep findings in integration gate\n\n* fix(ci): make gateway race performance gate stable\n\n* fix(ci): remove golangci schema network dependency\n\n* fix(ci): avoid redundant Lighthouse dependency bootstrap\n\n* fix(ci): close session crypto coverage branch\n\n* fix(ci): include workflow contract inputs in mutmut sandbox\n\n* fix(test): bound Miri sanitizer payload\n\n* fix(test): reduce Miri sanitizer fixture\n\n* fix(test): invalidate cached JWT keys on rotation\n\n* fix(test): isolate notification metrics state\n\n* chore: update codebase test coverage reports and configuration files\n\n* fix(ci): balance incremental mutmut shards\n\n* fix(test): clean up SPIFFE stress test lint\n\n* fix(test): isolate ChatWindow render suites\n\n* fix(frontend): guard profile sync auto-fetch reruns\n\n* fix(test): isolate profile coverage suites\n\n* fix(test): isolate component coverage suites\n\n* fix(test): isolate event hero coverage suites\n\n* fix(test): isolate schedule and event file suites\n\n* chore(test): checkpoint current branch changes\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-08T21:40:49+03:00",
          "tree_id": "26101b1ba5348abe8e9c0a22c539a733d8f96e1b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/496ed7f2c5c0fd33da738b4687b4c31281f14d7e"
        },
        "date": 1786214923323,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 554.7,
            "unit": "ns/op 192 B/op 2 allocs/op",
            "extra": "2168422 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 554.7,
            "unit": "ns/op",
            "extra": "2168422 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2168422 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2168422 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1497,
            "unit": "ns/op 376 B/op 10 allocs/op",
            "extra": "726115 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1497,
            "unit": "ns/op",
            "extra": "726115 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "726115 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "726115 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.78,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "87211476 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.78,
            "unit": "ns/op",
            "extra": "87211476 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "87211476 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "87211476 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 760.8,
            "unit": "ns/op 960 B/op 2 allocs/op",
            "extra": "1545085 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 760.8,
            "unit": "ns/op",
            "extra": "1545085 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1545085 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1545085 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 87.1,
            "unit": "ns/op 80 B/op 2 allocs/op",
            "extra": "13216183 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 87.1,
            "unit": "ns/op",
            "extra": "13216183 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13216183 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13216183 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1373,
            "unit": "ns/op 1856 B/op 2 allocs/op",
            "extra": "887206 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1373,
            "unit": "ns/op",
            "extra": "887206 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "887206 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "887206 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 34.75,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "34643382 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 34.75,
            "unit": "ns/op",
            "extra": "34643382 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "34643382 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "34643382 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1849,
            "unit": "ns/op 6879 B/op 8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1849,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6879,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 51.73,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "23161953 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 51.73,
            "unit": "ns/op",
            "extra": "23161953 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "23161953 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "23161953 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 700.1,
            "unit": "ns/op 640 B/op 8 allocs/op",
            "extra": "1709260 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 700.1,
            "unit": "ns/op",
            "extra": "1709260 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1709260 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1709260 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12984,
            "unit": "ns/op 16448 B/op 2 allocs/op",
            "extra": "93062 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12984,
            "unit": "ns/op",
            "extra": "93062 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93062 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93062 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada",
          "message": "ci(deps): Bump the github-actions group with 9 updates (#1230)\n\nBumps the github-actions group with 9 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [dtolnay/rust-toolchain](https://github.com/dtolnay/rust-toolchain) | `2c7215f132e9ebf062739d9130488b56d53c060c` | `6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.3114.0` | `12.3115.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `24.1.0` | `24.2.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.4` | `4.37.6` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.1` | `4.2.2` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.1` | `0.6.2` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/v7...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `dtolnay/rust-toolchain` from 2c7215f132e9ebf062739d9130488b56d53c060c to 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n- [Release notes](https://github.com/dtolnay/rust-toolchain/releases)\n- [Commits](https://github.com/dtolnay/rust-toolchain/compare/2c7215f132e9ebf062739d9130488b56d53c060c...6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772)\n\nUpdates `bridgecrewio/checkov-action` from 12.3114.0 to 12.3115.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/7b972723c44fb3d256283fac96fae5d7c1894bb7...9b70310bcd306d11740313070b940167d6b23085)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 24.1.0 to 24.2.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/6bf21b07787794f89a243495939cd651942aeabe...21c1be1b93ad9ed58fa840aacc3f279cde2a72ff)\n\nUpdates `github/codeql-action/init` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `github/codeql-action/analyze` from 4.37.4 to 4.37.6\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/f205ea1c3313d32999d8d6a48b4f6530d4437b38...5595ccaf912efad79be6eef63a5619ff05969be3)\n\nUpdates `actions/attest` from 4.2.1 to 4.2.2\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/508db95dd578ae2727ebd6217d5ba78e4fbda05d...1e69f48acb82d1966a394da916b4c1698aa569d6)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.1 to 0.6.2\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6fc4b006235f201fdab3722e17240ab420d580e5...3dc1ecc9bcb9e94e9b2c709687979e1298497054)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: 6c977a6ca4077a0ceb28ffbe03f59d46e9ac8772\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3115.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.6\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-10T12:31:09+03:00",
          "tree_id": "943e83367d58b7cd70d48bf646ef00f5ad5c36ce",
          "url": "https://github.com/egorribun/university_ecosystem/commit/8a8ab8e6e664fcefbf0d959dafacf0c9d44f2ada"
        },
        "date": 1786354516843,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 564.8,
            "unit": "ns/op 192 B/op 2 allocs/op",
            "extra": "2123908 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 564.8,
            "unit": "ns/op",
            "extra": "2123908 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2123908 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2123908 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1513,
            "unit": "ns/op 376 B/op 10 allocs/op",
            "extra": "717271 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1513,
            "unit": "ns/op",
            "extra": "717271 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "717271 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "717271 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.81,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "86561724 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.81,
            "unit": "ns/op",
            "extra": "86561724 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86561724 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86561724 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 793.8,
            "unit": "ns/op 960 B/op 2 allocs/op",
            "extra": "1530364 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 793.8,
            "unit": "ns/op",
            "extra": "1530364 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1530364 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1530364 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 89.29,
            "unit": "ns/op 80 B/op 2 allocs/op",
            "extra": "12752005 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 89.29,
            "unit": "ns/op",
            "extra": "12752005 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12752005 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12752005 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1420,
            "unit": "ns/op 1856 B/op 2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1420,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 34.83,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "34266517 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 34.83,
            "unit": "ns/op",
            "extra": "34266517 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "34266517 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "34266517 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1844,
            "unit": "ns/op 6879 B/op 8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1844,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6879,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 52.02,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "22990268 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 52.02,
            "unit": "ns/op",
            "extra": "22990268 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "22990268 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "22990268 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 703.2,
            "unit": "ns/op 640 B/op 8 allocs/op",
            "extra": "1714335 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 703.2,
            "unit": "ns/op",
            "extra": "1714335 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1714335 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1714335 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12887,
            "unit": "ns/op 16448 B/op 2 allocs/op",
            "extra": "92618 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12887,
            "unit": "ns/op",
            "extra": "92618 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "92618 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "92618 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "83beb35c866c4baa10b60e2ef95c663568a3c58e",
          "message": "build(deps): Bump the go-file-processor group (#1233)\n\nBumps the go-file-processor group in /services/file-processor with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/minio](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.temporal.io/api](https://github.com/temporalio/api-go) | `1.63.4` | `1.63.5` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/minio` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.temporal.io/api` from 1.63.4 to 1.63.5\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.4...v1.63.5)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/minio\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.5\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-11T14:12:40+03:00",
          "tree_id": "d51f68500e421c60f18e4437922edb661971e41a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/83beb35c866c4baa10b60e2ef95c663568a3c58e"
        },
        "date": 1786447281546,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 562.5,
            "unit": "ns/op 192 B/op 2 allocs/op",
            "extra": "2143470 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 562.5,
            "unit": "ns/op",
            "extra": "2143470 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2143470 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2143470 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1524,
            "unit": "ns/op 376 B/op 10 allocs/op",
            "extra": "708187 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1524,
            "unit": "ns/op",
            "extra": "708187 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "708187 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "708187 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.78,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "86771139 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.78,
            "unit": "ns/op",
            "extra": "86771139 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86771139 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86771139 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 801.3,
            "unit": "ns/op 960 B/op 2 allocs/op",
            "extra": "1523376 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 801.3,
            "unit": "ns/op",
            "extra": "1523376 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1523376 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1523376 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 88.29,
            "unit": "ns/op 80 B/op 2 allocs/op",
            "extra": "12999786 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 88.29,
            "unit": "ns/op",
            "extra": "12999786 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12999786 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12999786 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1392,
            "unit": "ns/op 1856 B/op 2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1392,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 34.8,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "34511203 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 34.8,
            "unit": "ns/op",
            "extra": "34511203 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "34511203 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "34511203 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1846,
            "unit": "ns/op 6879 B/op 8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1846,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6879,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 51.3,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "23209795 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 51.3,
            "unit": "ns/op",
            "extra": "23209795 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "23209795 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "23209795 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 710.3,
            "unit": "ns/op 640 B/op 8 allocs/op",
            "extra": "1692684 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 710.3,
            "unit": "ns/op",
            "extra": "1692684 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1692684 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1692684 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12913,
            "unit": "ns/op 16448 B/op 2 allocs/op",
            "extra": "93840 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12913,
            "unit": "ns/op",
            "extra": "93840 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93840 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93840 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2f04616dfc39026d11be988ae05d33eb9403f1c5",
          "message": "build(deps): Bump the go-ws-hub group (#1231)\n\nBumps the go-ws-hub group in /services/ws-hub with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/pact-foundation/pact-go/v2](https://github.com/pact-foundation/pact-go) | `2.5.1` | `2.7.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.60.0` | `0.61.0` |\n| [github.com/quic-go/webtransport-go](https://github.com/quic-go/webtransport-go) | `0.11.1` | `0.12.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/nats](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n\n\nUpdates `github.com/pact-foundation/pact-go/v2` from 2.5.1 to 2.7.0\n- [Release notes](https://github.com/pact-foundation/pact-go/releases)\n- [Changelog](https://github.com/pact-foundation/pact-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/pact-foundation/pact-go/compare/v2.5.1...v2.7.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `github.com/quic-go/quic-go` from 0.60.0 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.60.0...v0.61.0)\n\nUpdates `github.com/quic-go/webtransport-go` from 0.11.1 to 0.12.0\n- [Release notes](https://github.com/quic-go/webtransport-go/releases)\n- [Commits](https://github.com/quic-go/webtransport-go/compare/v0.11.1...v0.12.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/nats` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/pact-foundation/pact-go/v2\n  dependency-version: 2.7.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/quic-go/webtransport-go\n  dependency-version: 0.12.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/nats\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:07+03:00",
          "tree_id": "af20c3ca22f350fb2734115e77c0541b42988af5",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2f04616dfc39026d11be988ae05d33eb9403f1c5"
        },
        "date": 1786447568508,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 487.1,
            "unit": "ns/op 192 B/op 2 allocs/op",
            "extra": "2462972 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 487.1,
            "unit": "ns/op",
            "extra": "2462972 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2462972 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2462972 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1322,
            "unit": "ns/op 376 B/op 10 allocs/op",
            "extra": "783764 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1322,
            "unit": "ns/op",
            "extra": "783764 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "783764 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "783764 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.2,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "90345879 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.2,
            "unit": "ns/op",
            "extra": "90345879 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "90345879 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "90345879 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 758.9,
            "unit": "ns/op 960 B/op 2 allocs/op",
            "extra": "1572092 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 758.9,
            "unit": "ns/op",
            "extra": "1572092 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1572092 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1572092 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 87.66,
            "unit": "ns/op 80 B/op 2 allocs/op",
            "extra": "12973863 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 87.66,
            "unit": "ns/op",
            "extra": "12973863 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12973863 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12973863 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1356,
            "unit": "ns/op 1856 B/op 2 allocs/op",
            "extra": "978316 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1356,
            "unit": "ns/op",
            "extra": "978316 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "978316 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "978316 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 32.27,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "38955957 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 32.27,
            "unit": "ns/op",
            "extra": "38955957 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "38955957 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "38955957 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1793,
            "unit": "ns/op 6879 B/op 8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1793,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6879,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 46.3,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "26058615 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 46.3,
            "unit": "ns/op",
            "extra": "26058615 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "26058615 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "26058615 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 705.1,
            "unit": "ns/op 640 B/op 8 allocs/op",
            "extra": "1713024 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 705.1,
            "unit": "ns/op",
            "extra": "1713024 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1713024 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1713024 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 10401,
            "unit": "ns/op 16448 B/op 2 allocs/op",
            "extra": "115666 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 10401,
            "unit": "ns/op",
            "extra": "115666 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "115666 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "115666 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "49699333+dependabot[bot]@users.noreply.github.com",
            "name": "dependabot[bot]",
            "username": "dependabot[bot]"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "10c0ecff521b04524da5d7dd48aa9a93e8611647",
          "message": "build(deps): Bump the go-gateway group (#1232)\n\nBumps the go-gateway group in /services/gateway with 10 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github.com/quic-go/quic-go](https://github.com/quic-go/quic-go) | `0.59.1` | `0.61.0` |\n| [github.com/redis/go-redis/extra/redisprometheus/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/redis/go-redis/v9](https://github.com/redis/go-redis) | `9.21.0` | `9.22.0` |\n| [github.com/testcontainers/testcontainers-go](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [github.com/testcontainers/testcontainers-go/modules/redis](https://github.com/testcontainers/testcontainers-go) | `0.43.0` | `0.44.0` |\n| [go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin](https://github.com/open-telemetry/opentelemetry-go-contrib) | `0.69.0` | `0.70.0` |\n| [go.opentelemetry.io/otel](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/sdk](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n| [go.opentelemetry.io/otel/trace](https://github.com/open-telemetry/opentelemetry-go) | `1.44.0` | `1.45.0` |\n\n\nUpdates `github.com/quic-go/quic-go` from 0.59.1 to 0.61.0\n- [Release notes](https://github.com/quic-go/quic-go/releases)\n- [Commits](https://github.com/quic-go/quic-go/compare/v0.59.1...v0.61.0)\n\nUpdates `github.com/redis/go-redis/extra/redisprometheus/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/redis/go-redis/v9` from 9.21.0 to 9.22.0\n- [Release notes](https://github.com/redis/go-redis/releases)\n- [Changelog](https://github.com/redis/go-redis/blob/master/RELEASE-NOTES.md)\n- [Commits](https://github.com/redis/go-redis/compare/v9.21.0...v9.22.0)\n\nUpdates `github.com/testcontainers/testcontainers-go` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `github.com/testcontainers/testcontainers-go/modules/redis` from 0.43.0 to 0.44.0\n- [Release notes](https://github.com/testcontainers/testcontainers-go/releases)\n- [Commits](https://github.com/testcontainers/testcontainers-go/compare/v0.43.0...v0.44.0)\n\nUpdates `go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin` from 0.69.0 to 0.70.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go-contrib/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go-contrib/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go-contrib/compare/zpages/v0.69.0...zpages/v0.70.0)\n\nUpdates `go.opentelemetry.io/otel` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/sdk` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\nUpdates `go.opentelemetry.io/otel/trace` from 1.44.0 to 1.45.0\n- [Release notes](https://github.com/open-telemetry/opentelemetry-go/releases)\n- [Changelog](https://github.com/open-telemetry/opentelemetry-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/open-telemetry/opentelemetry-go/compare/v1.44.0...v1.45.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/quic-go/quic-go\n  dependency-version: 0.61.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/extra/redisprometheus/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/redis/go-redis/v9\n  dependency-version: 9.22.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/testcontainers/testcontainers-go/modules/redis\n  dependency-version: 0.44.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin\n  dependency-version: 0.70.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/sdk\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: go.opentelemetry.io/otel/trace\n  dependency-version: 1.45.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>\nCo-authored-by: Egor <egorribun2005@gmail.com>",
          "timestamp": "2026-08-11T14:13:36+03:00",
          "tree_id": "ca611e2a36d4ebc8176e6d30b8dc969e933c1748",
          "url": "https://github.com/egorribun/university_ecosystem/commit/10c0ecff521b04524da5d7dd48aa9a93e8611647"
        },
        "date": 1786447832420,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 431.2,
            "unit": "ns/op 192 B/op 2 allocs/op",
            "extra": "2772208 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 431.2,
            "unit": "ns/op",
            "extra": "2772208 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2772208 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2772208 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1164,
            "unit": "ns/op 376 B/op 10 allocs/op",
            "extra": "913182 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1164,
            "unit": "ns/op",
            "extra": "913182 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "913182 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "913182 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 17.69,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "67674340 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 17.69,
            "unit": "ns/op",
            "extra": "67674340 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "67674340 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "67674340 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 574,
            "unit": "ns/op 960 B/op 2 allocs/op",
            "extra": "2080884 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 574,
            "unit": "ns/op",
            "extra": "2080884 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "2080884 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2080884 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 67.86,
            "unit": "ns/op 80 B/op 2 allocs/op",
            "extra": "16495071 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 67.86,
            "unit": "ns/op",
            "extra": "16495071 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "16495071 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "16495071 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1072,
            "unit": "ns/op 1856 B/op 2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1072,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 44.49,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "26790788 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 44.49,
            "unit": "ns/op",
            "extra": "26790788 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "26790788 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "26790788 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1698,
            "unit": "ns/op 6879 B/op 8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1698,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6879,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 58.79,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "20418956 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 58.79,
            "unit": "ns/op",
            "extra": "20418956 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "20418956 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "20418956 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 596.3,
            "unit": "ns/op 640 B/op 8 allocs/op",
            "extra": "2014186 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 596.3,
            "unit": "ns/op",
            "extra": "2014186 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "2014186 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "2014186 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 10625,
            "unit": "ns/op 16448 B/op 2 allocs/op",
            "extra": "116588 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 10625,
            "unit": "ns/op",
            "extra": "116588 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "116588 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "116588 times\n4 procs"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "egorribun2005@gmail.com",
            "name": "Egor",
            "username": "egorribun"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667",
          "message": "feat(quality): bootstrap trusted performance assets (#1234)\n\nasset bootstrap / no safe preexisting required context; base is missing base-trusted performance tooling; retaining path filter avoids widening legacy writable PR workflow.\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-11T20:19:16+03:00",
          "tree_id": "e6ce87a619a6dd553eef22861034220a6828012c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/fdf9a6ea8b9d1b222f51dc4a2c7ed3b57f91e667"
        },
        "date": 1786469012985,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 479.7,
            "unit": "ns/op 192 B/op 2 allocs/op",
            "extra": "2508102 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 479.7,
            "unit": "ns/op",
            "extra": "2508102 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2508102 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2508102 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1341,
            "unit": "ns/op 376 B/op 10 allocs/op",
            "extra": "814196 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1341,
            "unit": "ns/op",
            "extra": "814196 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "814196 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "814196 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.17,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "90510788 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.17,
            "unit": "ns/op",
            "extra": "90510788 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "90510788 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "90510788 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 773.3,
            "unit": "ns/op 960 B/op 2 allocs/op",
            "extra": "1550847 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 773.3,
            "unit": "ns/op",
            "extra": "1550847 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1550847 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1550847 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 88.04,
            "unit": "ns/op 80 B/op 2 allocs/op",
            "extra": "12730825 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 88.04,
            "unit": "ns/op",
            "extra": "12730825 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12730825 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12730825 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1392,
            "unit": "ns/op 1856 B/op 2 allocs/op",
            "extra": "923365 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1392,
            "unit": "ns/op",
            "extra": "923365 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - B/op",
            "value": 1856,
            "unit": "B/op",
            "extra": "923365 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "923365 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 30.93,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "37018035 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 30.93,
            "unit": "ns/op",
            "extra": "37018035 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "37018035 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "37018035 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1793,
            "unit": "ns/op 6879 B/op 8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1793,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6879,
            "unit": "B/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 46.19,
            "unit": "ns/op 0 B/op 0 allocs/op",
            "extra": "25728338 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 46.19,
            "unit": "ns/op",
            "extra": "25728338 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25728338 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25728338 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 706.7,
            "unit": "ns/op 640 B/op 8 allocs/op",
            "extra": "1698174 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 706.7,
            "unit": "ns/op",
            "extra": "1698174 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1698174 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1698174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 10583,
            "unit": "ns/op 16448 B/op 2 allocs/op",
            "extra": "113168 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 10583,
            "unit": "ns/op",
            "extra": "113168 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "113168 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "113168 times\n4 procs"
          }
        ]
      }
    ]
  }
}