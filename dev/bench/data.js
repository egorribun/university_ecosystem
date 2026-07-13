window.BENCHMARK_DATA = {
  "lastUpdate": 1783972091487,
  "repoUrl": "https://github.com/egorribun/university_ecosystem",
  "entries": {
    "Go Services Performance Benchmarks": [
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
          "id": "a4a29b04668a6d590ca126519cebf261fb5bc4d9",
          "message": "chore: trigger benchmark deployment\n\n* chore: trigger CI and benchmark workflows\n\n* chore: trigger CI and benchmark deployment",
          "timestamp": "2026-07-06T04:02:56+03:00",
          "tree_id": "0c4444c198891cd69758e0defb6bd6e86fa39395",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a4a29b04668a6d590ca126519cebf261fb5bc4d9"
        },
        "date": 1783299984975,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 867.4,
            "unit": "ns/op",
            "extra": "1361013 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.65,
            "unit": "ns/op",
            "extra": "17473732 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 154.9,
            "unit": "ns/op",
            "extra": "7948222 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 11.58,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 541.2,
            "unit": "ns/op",
            "extra": "2163150 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 66.33,
            "unit": "ns/op",
            "extra": "18157378 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.96,
            "unit": "ns/op",
            "extra": "39479967 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 563.9,
            "unit": "ns/op",
            "extra": "2117217 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1539,
            "unit": "ns/op",
            "extra": "747750 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14.21,
            "unit": "ns/op",
            "extra": "86755330 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 799.5,
            "unit": "ns/op",
            "extra": "1505751 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 92.75,
            "unit": "ns/op",
            "extra": "12847477 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1426,
            "unit": "ns/op",
            "extra": "759524 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 22.14,
            "unit": "ns/op",
            "extra": "55143109 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1588,
            "unit": "ns/op",
            "extra": "745560 times\n4 procs"
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
          "id": "35f3049c4a9b1b07018d294d4e630095e23828a6",
          "message": "chore: fix TruffleHog BASE and HEAD same commit push error\n\n* chore: trigger CI and benchmark workflows\n\n* chore: fix TruffleHog 'BASE and HEAD commits are the same' push error",
          "timestamp": "2026-07-06T04:34:52+03:00",
          "tree_id": "f8bbd3be4bb17f8cb074f32b4f270d766a2a08f2",
          "url": "https://github.com/egorribun/university_ecosystem/commit/35f3049c4a9b1b07018d294d4e630095e23828a6"
        },
        "date": 1783301873736,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 865.3,
            "unit": "ns/op",
            "extra": "1386940 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.7,
            "unit": "ns/op",
            "extra": "17439621 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 151.1,
            "unit": "ns/op",
            "extra": "7955697 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 11.31,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 540.9,
            "unit": "ns/op",
            "extra": "2160981 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 65.92,
            "unit": "ns/op",
            "extra": "17957394 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 32.66,
            "unit": "ns/op",
            "extra": "37598869 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 566.5,
            "unit": "ns/op",
            "extra": "2061780 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1570,
            "unit": "ns/op",
            "extra": "701355 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.88,
            "unit": "ns/op",
            "extra": "87011482 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 939.9,
            "unit": "ns/op",
            "extra": "1527667 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 92.52,
            "unit": "ns/op",
            "extra": "12606598 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1492,
            "unit": "ns/op",
            "extra": "782186 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.76,
            "unit": "ns/op",
            "extra": "55264542 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1633,
            "unit": "ns/op",
            "extra": "753213 times\n4 procs"
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
          "id": "481a1f1ca2d3c64d35ebafe59d422637223be593",
          "message": "ci(deps): Bump the github-actions group with 18 updates\n\nBumps the github-actions group with 18 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.2.0` | `8.3.0` |\n| [bridgecrewio/checkov-action](https://github.com/bridgecrewio/checkov-action) | `12.2884.0` | `12.3112.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.36.2` | `4.36.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `17.7.2` | `18.0.1` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `19.1.0` | `24.0.0` |\n| [streetsidesoftware/cspell-action](https://github.com/streetsidesoftware/cspell-action) | `6.2.0` | `8.4.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.36.2` | `4.36.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.36.2` | `4.36.3` |\n| [gitleaks/gitleaks-action](https://github.com/gitleaks/gitleaks-action) | `2.3.9` | `3.0.0` |\n| [golangci/golangci-lint-action](https://github.com/golangci/golangci-lint-action) | `9.2.1` | `9.3.0` |\n| [zaproxy/action-baseline](https://github.com/zaproxy/action-baseline) | `6c5a007541891231cd9e0ddec25d4f25c59c9874` | `de8ad967d3548d44ef623df22cf95c3b0baf8b25` |\n| [codecov/codecov-action](https://github.com/codecov/codecov-action) | `5.3.0` | `7.0.0` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.2.0` | `4.4.0` |\n| [docker/setup-buildx-action](https://github.com/docker/setup-buildx-action) | `4.1.0` | `4.2.0` |\n| [docker/build-push-action](https://github.com/docker/build-push-action) | `7.2.0` | `7.3.0` |\n| [amannn/action-semantic-pull-request](https://github.com/amannn/action-semantic-pull-request) | `2d952a1bf90a6a7ab8f0293dc86f5fdf9acb1915` | `2c9480cf285c2ac02b52e26013f7d627b14a4f95` |\n| [SonarSource/sonarqube-scan-action](https://github.com/sonarsource/sonarqube-scan-action) | `5.0.0` | `8.2.0` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.90.5` | `3.95.8` |\n\n\nUpdates `astral-sh/setup-uv` from 8.2.0 to 8.3.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/fac544c07dec837d0ccb6301d7b5580bf5edae39...d31148d669074a8d0a63714ba94f3201e7020bc3)\n\nUpdates `bridgecrewio/checkov-action` from 12.2884.0 to 12.3112.0\n- [Release notes](https://github.com/bridgecrewio/checkov-action/releases)\n- [Commits](https://github.com/bridgecrewio/checkov-action/compare/a36096a3a272a684d48058e101498cddb9a1599d...a7683e7b72a04503521247973281ec8142e1ac1f)\n\nUpdates `github/codeql-action/upload-sarif` from 4.36.2 to 4.36.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...54f647b7e1bb85c95cddabcd46b0c578ec92bc1a)\n\nUpdates `chromaui/action` from 17.7.2 to 18.0.1\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/7ffa9343588f15ff3f4cde30e03cd23204ed6a9c...94713c544284a14195de3b50ef24301579f1877e)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 19.1.0 to 24.0.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/05f32210e84442804257b2a6f20b273450ec8265...8de2aa07cae85fd17c0b35642db70cf5495f1d25)\n\nUpdates `streetsidesoftware/cspell-action` from 6.2.0 to 8.4.0\n- [Release notes](https://github.com/streetsidesoftware/cspell-action/releases)\n- [Changelog](https://github.com/streetsidesoftware/cspell-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/streetsidesoftware/cspell-action/compare/807d7d92b7057593a2de102168506f298405339d...de2a73e963e7443969755b648a1008f77033c5b2)\n\nUpdates `github/codeql-action/init` from 4.36.2 to 4.36.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...54f647b7e1bb85c95cddabcd46b0c578ec92bc1a)\n\nUpdates `github/codeql-action/analyze` from 4.36.2 to 4.36.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/8aad20d150bbac5944a9f9d289da16a4b0d87c1e...54f647b7e1bb85c95cddabcd46b0c578ec92bc1a)\n\nUpdates `gitleaks/gitleaks-action` from 2.3.9 to 3.0.0\n- [Release notes](https://github.com/gitleaks/gitleaks-action/releases)\n- [Commits](https://github.com/gitleaks/gitleaks-action/compare/ff98106e4c7b2bc287b24eaf42907196329070c7...e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e)\n\nUpdates `golangci/golangci-lint-action` from 9.2.1 to 9.3.0\n- [Release notes](https://github.com/golangci/golangci-lint-action/releases)\n- [Commits](https://github.com/golangci/golangci-lint-action/compare/82606bf257cbaff209d206a39f5134f0cfbfd2ee...ba0d7d2ec06a0ea1cb5fa41b2e4a3ab91d21278a)\n\nUpdates `zaproxy/action-baseline` from 6c5a007541891231cd9e0ddec25d4f25c59c9874 to de8ad967d3548d44ef623df22cf95c3b0baf8b25\n- [Release notes](https://github.com/zaproxy/action-baseline/releases)\n- [Changelog](https://github.com/zaproxy/action-baseline/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/zaproxy/action-baseline/compare/6c5a007541891231cd9e0ddec25d4f25c59c9874...de8ad967d3548d44ef623df22cf95c3b0baf8b25)\n\nUpdates `codecov/codecov-action` from 5.3.0 to 7.0.0\n- [Release notes](https://github.com/codecov/codecov-action/releases)\n- [Changelog](https://github.com/codecov/codecov-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/codecov/codecov-action/compare/0da7aa657d958d32c117fc47e1f977e7524753c7...fb8b3582c8e4def4969c97caa2f19720cb33a72f)\n\nUpdates `docker/login-action` from 4.2.0 to 4.4.0\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/650006c6eb7dba73a995cc03b0b2d7f5ca915bee...af1e73f918a031802d376d3c8bbc3fe56130a9b0)\n\nUpdates `docker/setup-buildx-action` from 4.1.0 to 4.2.0\n- [Release notes](https://github.com/docker/setup-buildx-action/releases)\n- [Commits](https://github.com/docker/setup-buildx-action/compare/d7f5e7f509e45cec5c76c4d5afdd7de93d0b3df5...bb05f3f5519dd87d3ba754cc423b652a5edd6d2c)\n\nUpdates `docker/build-push-action` from 7.2.0 to 7.3.0\n- [Release notes](https://github.com/docker/build-push-action/releases)\n- [Commits](https://github.com/docker/build-push-action/compare/f9f3042f7e2789586610d6e8b85c8f03e5195baf...53b7df96c91f9c12dcc8a07bcb9ccacbed38856a)\n\nUpdates `amannn/action-semantic-pull-request` from 2d952a1bf90a6a7ab8f0293dc86f5fdf9acb1915 to 2c9480cf285c2ac02b52e26013f7d627b14a4f95\n- [Release notes](https://github.com/amannn/action-semantic-pull-request/releases)\n- [Changelog](https://github.com/amannn/action-semantic-pull-request/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/amannn/action-semantic-pull-request/compare/2d952a1bf90a6a7ab8f0293dc86f5fdf9acb1915...2c9480cf285c2ac02b52e26013f7d627b14a4f95)\n\nUpdates `SonarSource/sonarqube-scan-action` from 5.0.0 to 8.2.0\n- [Release notes](https://github.com/sonarsource/sonarqube-scan-action/releases)\n- [Commits](https://github.com/sonarsource/sonarqube-scan-action/compare/0303d6b62e310685c0e34d0b9cde218036885c4d...713881670b6b3676cda39549040e2d88c70d582e)\n\nUpdates `trufflesecurity/trufflehog` from 3.90.5 to 3.95.8\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/0f58ae7c5036094a1e3e750d18772af92821b503...00155c9dc586f34d189adc83d3ac2698c2ec551f)\n\n---\nupdated-dependencies:\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 8.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3112.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.36.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: streetsidesoftware/cspell-action\n  dependency-version: 8.4.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.36.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.36.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: gitleaks/gitleaks-action\n  dependency-version: 3.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: golangci/golangci-lint-action\n  dependency-version: 9.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zaproxy/action-baseline\n  dependency-version: de8ad967d3548d44ef623df22cf95c3b0baf8b25\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: codecov/codecov-action\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.4.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: docker/setup-buildx-action\n  dependency-version: 4.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: docker/build-push-action\n  dependency-version: 7.3.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: amannn/action-semantic-pull-request\n  dependency-version: 2c9480cf285c2ac02b52e26013f7d627b14a4f95\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: SonarSource/sonarqube-scan-action\n  dependency-version: 8.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.95.8\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-06T17:10:06+03:00",
          "tree_id": "7c69753d65d991c3d36e927dad468c92e25383e4",
          "url": "https://github.com/egorribun/university_ecosystem/commit/481a1f1ca2d3c64d35ebafe59d422637223be593"
        },
        "date": 1783347108850,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 783.6,
            "unit": "ns/op",
            "extra": "1530552 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.4,
            "unit": "ns/op",
            "extra": "16593139 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 165.7,
            "unit": "ns/op",
            "extra": "7255557 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 10.81,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 509.7,
            "unit": "ns/op",
            "extra": "2358272 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 74.92,
            "unit": "ns/op",
            "extra": "16059434 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 28.35,
            "unit": "ns/op",
            "extra": "39150666 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 478.8,
            "unit": "ns/op",
            "extra": "2501343 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1302,
            "unit": "ns/op",
            "extra": "776780 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.39,
            "unit": "ns/op",
            "extra": "90998565 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 726.8,
            "unit": "ns/op",
            "extra": "1442647 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 88.75,
            "unit": "ns/op",
            "extra": "13688415 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1337,
            "unit": "ns/op",
            "extra": "844311 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.15,
            "unit": "ns/op",
            "extra": "56277880 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1573,
            "unit": "ns/op",
            "extra": "779893 times\n4 procs"
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
          "id": "ae11edc3736abd35a2bde612c12df103594289e3",
          "message": "build(deps): Update fastapi requirement from <0.139,>=0.135.3 to >=0.135.3,<0.140 in the pip-dependencies group\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi) to permit the latest version.\n\nUpdates `fastapi` to 0.139.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.139.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.139.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-06T17:09:54+03:00",
          "tree_id": "29959c8fc175396fe56d40dcf0ac5fdffedc0a16",
          "url": "https://github.com/egorribun/university_ecosystem/commit/ae11edc3736abd35a2bde612c12df103594289e3"
        },
        "date": 1783347112072,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 791.8,
            "unit": "ns/op",
            "extra": "1525677 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.58,
            "unit": "ns/op",
            "extra": "16542044 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 165.9,
            "unit": "ns/op",
            "extra": "6802233 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 10.99,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 508.2,
            "unit": "ns/op",
            "extra": "2375888 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 74.14,
            "unit": "ns/op",
            "extra": "16185931 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 28.66,
            "unit": "ns/op",
            "extra": "38916284 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 482.1,
            "unit": "ns/op",
            "extra": "2477360 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1309,
            "unit": "ns/op",
            "extra": "833271 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.22,
            "unit": "ns/op",
            "extra": "91018443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 741.3,
            "unit": "ns/op",
            "extra": "1630558 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 88.53,
            "unit": "ns/op",
            "extra": "13355113 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1359,
            "unit": "ns/op",
            "extra": "858609 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.08,
            "unit": "ns/op",
            "extra": "57358695 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1564,
            "unit": "ns/op",
            "extra": "757826 times\n4 procs"
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
          "id": "ac92b400cfb729e6aa4f2f4175ec8514a3d094b4",
          "message": "feat: complete full testing roadmap + OSS-Fuzz integration\n\nfeat: complete testing roadmap (Pytest, Go, Rust, Frontend, E2E)",
          "timestamp": "2026-07-07T18:00:35+03:00",
          "tree_id": "0657d0644d5d783cc87c9c89f1c4465790781d70",
          "url": "https://github.com/egorribun/university_ecosystem/commit/ac92b400cfb729e6aa4f2f4175ec8514a3d094b4"
        },
        "date": 1783436546395,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 108459,
            "unit": "ns/op",
            "extra": "10000 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 111.1,
            "unit": "ns/op",
            "extra": "10718601 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 854,
            "unit": "ns/op",
            "extra": "1410582 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 69.23,
            "unit": "ns/op",
            "extra": "17329238 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 151.2,
            "unit": "ns/op",
            "extra": "7955028 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 11.5,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 551.3,
            "unit": "ns/op",
            "extra": "2181519 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 65.97,
            "unit": "ns/op",
            "extra": "18219570 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 30.24,
            "unit": "ns/op",
            "extra": "37361822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 571.2,
            "unit": "ns/op",
            "extra": "2113737 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1533,
            "unit": "ns/op",
            "extra": "706986 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 14.09,
            "unit": "ns/op",
            "extra": "85289403 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 775.8,
            "unit": "ns/op",
            "extra": "1593498 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 93.59,
            "unit": "ns/op",
            "extra": "12721027 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1449,
            "unit": "ns/op",
            "extra": "748315 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 21.76,
            "unit": "ns/op",
            "extra": "54907515 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1521,
            "unit": "ns/op",
            "extra": "789013 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 41.62,
            "unit": "ns/op",
            "extra": "29374474 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 780.8,
            "unit": "ns/op",
            "extra": "1500759 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 15741,
            "unit": "ns/op",
            "extra": "76726 times\n4 procs"
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
          "id": "cf66cebab3789eeb20c055ebb4fe402a70ac3359",
          "message": "feat: maximum coverage roadmap implementation\n\n* feat(wave212): maximum coverage roadmap implementation\n\n* chore: update agents.md testing constraint rules\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-07-13T22:43:20+03:00",
          "tree_id": "80a604c64e5d60a79a8bc236c61d9dcc3a9c8aa2",
          "url": "https://github.com/egorribun/university_ecosystem/commit/cf66cebab3789eeb20c055ebb4fe402a70ac3359"
        },
        "date": 1783972036181,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation",
            "value": 121770,
            "unit": "ns/op",
            "extra": "9520 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback",
            "value": 111.8,
            "unit": "ns/op",
            "extra": "10727035 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader",
            "value": 876.6,
            "unit": "ns/op",
            "extra": "1383733 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT",
            "value": 69.03,
            "unit": "ns/op",
            "extra": "17286730 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit",
            "value": 150.8,
            "unit": "ns/op",
            "extra": "7958887 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss",
            "value": 11.37,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey",
            "value": 553.6,
            "unit": "ns/op",
            "extra": "1846310 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic",
            "value": 65.94,
            "unit": "ns/op",
            "extra": "18209289 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256",
            "value": 30.23,
            "unit": "ns/op",
            "extra": "37923006 times\n4 procs"
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
          "id": "7e8215429e3ceea051bf51e9c0642a9b4e669e84",
          "message": "ci(deps): Bump the github-actions group with 9 updates\n\n---\nupdated-dependencies:\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 8.3.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: fa04a1451ff1842e2626ccb99004d0195b455a88\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: actions/cache\n  dependency-version: 6.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: bridgecrewio/checkov-action\n  dependency-version: 12.3114.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.95.9\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-13T22:43:37+03:00",
          "tree_id": "01308c2aa49e8873c0549849d5a2b47e6b6fb984",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7e8215429e3ceea051bf51e9c0642a9b4e669e84"
        },
        "date": 1783972090962,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation",
            "value": 119546,
            "unit": "ns/op",
            "extra": "9436 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback",
            "value": 111.4,
            "unit": "ns/op",
            "extra": "10666746 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader",
            "value": 869.5,
            "unit": "ns/op",
            "extra": "1343544 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT",
            "value": 70.2,
            "unit": "ns/op",
            "extra": "17332734 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit",
            "value": 152.6,
            "unit": "ns/op",
            "extra": "7690540 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss",
            "value": 11.37,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey",
            "value": 552.1,
            "unit": "ns/op",
            "extra": "2164153 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic",
            "value": 65.98,
            "unit": "ns/op",
            "extra": "18189192 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256",
            "value": 30.43,
            "unit": "ns/op",
            "extra": "38492582 times\n4 procs"
          }
        ]
      }
    ]
  }
}