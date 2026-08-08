window.BENCHMARK_DATA = {
  "lastUpdate": 1786214797297,
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
          "id": "ecdd7e91f64cec8f9201df4280fe9514a8aa66c3",
          "message": "build(deps-dev): Update mypy requirement from <2.2,>=1.20.1 to >=1.20.1,<2.3 in the pip-dependencies group\n\nUpdates the requirements on [mypy](https://github.com/python/mypy) to permit the latest version.\n\nUpdates `mypy` to 2.2.0\n- [Changelog](https://github.com/python/mypy/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/python/mypy/compare/v1.20.1...v2.2.0)\n\n---\nupdated-dependencies:\n- dependency-name: mypy\n  dependency-version: 2.2.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-13T22:43:54+03:00",
          "tree_id": "fbc729bc609e7e9cace409865c738e2d55e49e52",
          "url": "https://github.com/egorribun/university_ecosystem/commit/ecdd7e91f64cec8f9201df4280fe9514a8aa66c3"
        },
        "date": 1783972219689,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation",
            "value": 98035,
            "unit": "ns/op",
            "extra": "12086 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback",
            "value": 106.9,
            "unit": "ns/op",
            "extra": "10769394 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader",
            "value": 785.4,
            "unit": "ns/op",
            "extra": "1521699 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT",
            "value": 73.6,
            "unit": "ns/op",
            "extra": "16454437 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit",
            "value": 167.8,
            "unit": "ns/op",
            "extra": "7240312 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss",
            "value": 10.95,
            "unit": "ns/op",
            "extra": "100000000 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey",
            "value": 514.7,
            "unit": "ns/op",
            "extra": "2322836 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic",
            "value": 74.38,
            "unit": "ns/op",
            "extra": "15600986 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256",
            "value": 28.48,
            "unit": "ns/op",
            "extra": "39671395 times\n4 procs"
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
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817265712,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 45364,
            "unit": "ns/op",
            "extra": "23020 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 72.31,
            "unit": "ns/op",
            "extra": "16794429 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 523,
            "unit": "ns/op",
            "extra": "2097452 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 45.03,
            "unit": "ns/op",
            "extra": "26591865 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 82.45,
            "unit": "ns/op",
            "extra": "14707543 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 26.93,
            "unit": "ns/op",
            "extra": "44604332 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 361.5,
            "unit": "ns/op",
            "extra": "3336584 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 49.43,
            "unit": "ns/op",
            "extra": "24268316 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 18.06,
            "unit": "ns/op",
            "extra": "66259995 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 349.5,
            "unit": "ns/op",
            "extra": "3435222 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 963.6,
            "unit": "ns/op",
            "extra": "1249096 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 15.85,
            "unit": "ns/op",
            "extra": "75540339 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 503.3,
            "unit": "ns/op",
            "extra": "2328672 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 67.68,
            "unit": "ns/op",
            "extra": "21312800 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 890.7,
            "unit": "ns/op",
            "extra": "1378123 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 50.19,
            "unit": "ns/op",
            "extra": "23457670 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1595,
            "unit": "ns/op",
            "extra": "913264 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 58.67,
            "unit": "ns/op",
            "extra": "20337366 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 564.6,
            "unit": "ns/op",
            "extra": "2038251 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 12019,
            "unit": "ns/op",
            "extra": "123360 times\n4 procs"
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
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191585252,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 119108,
            "unit": "ns/op",
            "extra": "9496 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 108.6,
            "unit": "ns/op",
            "extra": "10949688 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 881.4,
            "unit": "ns/op",
            "extra": "1379823 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 68.97,
            "unit": "ns/op",
            "extra": "16641957 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 95.6,
            "unit": "ns/op",
            "extra": "12737086 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 15.78,
            "unit": "ns/op",
            "extra": "76777784 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 572.1,
            "unit": "ns/op",
            "extra": "2067961 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 66.71,
            "unit": "ns/op",
            "extra": "18030350 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 29.8,
            "unit": "ns/op",
            "extra": "39339982 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 572,
            "unit": "ns/op",
            "extra": "2087900 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1510,
            "unit": "ns/op",
            "extra": "711382 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 13.81,
            "unit": "ns/op",
            "extra": "87134408 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 848.9,
            "unit": "ns/op",
            "extra": "1423854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 91.72,
            "unit": "ns/op",
            "extra": "12508275 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1501,
            "unit": "ns/op",
            "extra": "830784 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 49.24,
            "unit": "ns/op",
            "extra": "21722012 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 2010,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 63.05,
            "unit": "ns/op",
            "extra": "18966276 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 787.5,
            "unit": "ns/op",
            "extra": "1543544 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 18002,
            "unit": "ns/op",
            "extra": "91990 times\n4 procs"
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
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191779408,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkJWKSValidation (github.com/university-ecosystem/gateway/middleware)",
            "value": 53097,
            "unit": "ns/op",
            "extra": "22018 times\n4 procs"
          },
          {
            "name": "BenchmarkRateLimitFallback (github.com/university-ecosystem/gateway/middleware)",
            "value": 75.65,
            "unit": "ns/op",
            "extra": "15789477 times\n4 procs"
          },
          {
            "name": "BenchmarkExtractAlgFromHeader (github.com/university-ecosystem/gateway/middleware)",
            "value": 546.2,
            "unit": "ns/op",
            "extra": "2166018 times\n4 procs"
          },
          {
            "name": "BenchmarkValidateIAT (github.com/university-ecosystem/gateway/middleware)",
            "value": 47.27,
            "unit": "ns/op",
            "extra": "22206970 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Hit (github.com/university-ecosystem/gateway/middleware)",
            "value": 83.9,
            "unit": "ns/op",
            "extra": "14285337 times\n4 procs"
          },
          {
            "name": "BenchmarkCheckL1Cache_Miss (github.com/university-ecosystem/gateway/middleware)",
            "value": 27.73,
            "unit": "ns/op",
            "extra": "43300068 times\n4 procs"
          },
          {
            "name": "BenchmarkJWKToRSAPublicKey (github.com/university-ecosystem/gateway/middleware)",
            "value": 427.7,
            "unit": "ns/op",
            "extra": "3146215 times\n4 procs"
          },
          {
            "name": "BenchmarkShouldRefreshProbabilistic (github.com/university-ecosystem/gateway/middleware)",
            "value": 50.73,
            "unit": "ns/op",
            "extra": "23630672 times\n4 procs"
          },
          {
            "name": "BenchmarkKeyFunc_HS256 (github.com/university-ecosystem/gateway/middleware)",
            "value": 20.35,
            "unit": "ns/op",
            "extra": "58703770 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 369.1,
            "unit": "ns/op",
            "extra": "3296347 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1071,
            "unit": "ns/op",
            "extra": "1184059 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 16.28,
            "unit": "ns/op",
            "extra": "73781942 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 522,
            "unit": "ns/op",
            "extra": "2240871 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 66.51,
            "unit": "ns/op",
            "extra": "20231965 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 910.8,
            "unit": "ns/op",
            "extra": "1240654 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 52.92,
            "unit": "ns/op",
            "extra": "26020887 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 1647,
            "unit": "ns/op",
            "extra": "899900 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 61.63,
            "unit": "ns/op",
            "extra": "19880168 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 604,
            "unit": "ns/op",
            "extra": "1941637 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients (github.com/university-ecosystem/ws-hub/pkg/hub)",
            "value": 12613,
            "unit": "ns/op",
            "extra": "122295 times\n4 procs"
          }
        ]
      }
    ],
    "Rust Criterion Benchmarks (pyo3-sanitizer)": [
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
          "id": "01f5225769cacda2c9a609e9100b5b74cf5e5990",
          "message": "build(deps): Bump the pip-dependencies group with 2 updates\n\nUpdates the requirements on [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [mypy](https://github.com/python/mypy) to permit the latest version.\n\nUpdates `strawberry-graphql` to 0.322.0\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `mypy` to 2.3.0\n- [Changelog](https://github.com/python/mypy/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/python/mypy/compare/v1.20.1...v2.3.0)\n\n---\nupdated-dependencies:\n- dependency-name: strawberry-graphql\n  dependency-version: 0.322.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: mypy\n  dependency-version: 2.3.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:53:21+03:00",
          "tree_id": "d4c90f0e6becfd187a1204cb3e998d104cc53a8b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/01f5225769cacda2c9a609e9100b5b74cf5e5990"
        },
        "date": 1784638726411,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5647,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6501,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9211,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 9584,
            "range": "± 45",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 92606,
            "range": "± 221",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5128,
            "range": "± 71",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 5954,
            "range": "± 74",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8503,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 8546,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 87174,
            "range": "± 214",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5026,
            "range": "± 71",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 5826,
            "range": "± 9",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8072,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 8409,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 85567,
            "range": "± 412",
            "unit": "ns/iter"
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
          "id": "e261ba2563a976605c4ab10149f3e7c7fd093085",
          "message": "ci(deps): Bump the github-actions group with 13 updates\n\nBumps the github-actions group with 13 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/setup-node](https://github.com/actions/setup-node) | `6.4.0` | `7.0.0` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.0` | `8.3.2` |\n| [actions/setup-go](https://github.com/actions/setup-go) | `6.5.0` | `7.0.0` |\n| [dtolnay/rust-toolchain](https://github.com/dtolnay/rust-toolchain) | `fa04a1451ff1842e2626ccb99004d0195b455a88` | `2c7215f132e9ebf062739d9130488b56d53c060c` |\n| [EmbarkStudios/cargo-deny-action](https://github.com/embarkstudios/cargo-deny-action) | `2.0.20` | `2.1.1` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.0` | `4.37.1` |\n| [DavidAnson/markdownlint-cli2-action](https://github.com/davidanson/markdownlint-cli2-action) | `24.0.0` | `24.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.0` | `4.37.1` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.0` | `4.37.1` |\n| [actions/attest](https://github.com/actions/attest) | `4.1.1` | `4.2.0` |\n| [SonarSource/sonarqube-scan-action](https://github.com/sonarsource/sonarqube-scan-action) | `8.2.0` | `8.2.1` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.5.7` | `0.6.0` |\n\n\nUpdates `actions/setup-node` from 6.4.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-node/releases)\n- [Commits](https://github.com/actions/setup-node/compare/48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e...820762786026740c76f36085b0efc47a31fe5020)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/ece7cb06caefa5fff74198d8649806c4678c61a1...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.0 to 8.3.2\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/v8.3.0...11f9893b081a58869d3b5fccaea48c9e9e46f990)\n\nUpdates `actions/setup-go` from 6.5.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-go/releases)\n- [Commits](https://github.com/actions/setup-go/compare/924ae3a1cded613372ab5595356fb5720e22ba16...b7ad1dad31e06c5925ef5d2fc7ad053ef454303e)\n\nUpdates `dtolnay/rust-toolchain` from fa04a1451ff1842e2626ccb99004d0195b455a88 to 2c7215f132e9ebf062739d9130488b56d53c060c\n- [Release notes](https://github.com/dtolnay/rust-toolchain/releases)\n- [Commits](https://github.com/dtolnay/rust-toolchain/compare/fa04a1451ff1842e2626ccb99004d0195b455a88...2c7215f132e9ebf062739d9130488b56d53c060c)\n\nUpdates `EmbarkStudios/cargo-deny-action` from 2.0.20 to 2.1.1\n- [Release notes](https://github.com/embarkstudios/cargo-deny-action/releases)\n- [Commits](https://github.com/embarkstudios/cargo-deny-action/compare/bb137d7af7e4fb67e5f82a49c4fce4fad40782fe...3c6349835b2b7b196a839186cb8b78e02f7b5f25)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.0 to 4.37.1\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/99df26d4f13ea111d4ec1a7dddef6063f76b97e9...7188fc363630916deb702c7fdcf4e481b751f97a)\n\nUpdates `DavidAnson/markdownlint-cli2-action` from 24.0.0 to 24.1.0\n- [Release notes](https://github.com/davidanson/markdownlint-cli2-action/releases)\n- [Commits](https://github.com/davidanson/markdownlint-cli2-action/compare/8de2aa07cae85fd17c0b35642db70cf5495f1d25...6bf21b07787794f89a243495939cd651942aeabe)\n\nUpdates `github/codeql-action/init` from 4.37.0 to 4.37.1\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/99df26d4f13ea111d4ec1a7dddef6063f76b97e9...7188fc363630916deb702c7fdcf4e481b751f97a)\n\nUpdates `github/codeql-action/analyze` from 4.37.0 to 4.37.1\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/99df26d4f13ea111d4ec1a7dddef6063f76b97e9...7188fc363630916deb702c7fdcf4e481b751f97a)\n\nUpdates `actions/attest` from 4.1.1 to 4.2.0\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/a1948c3f048ba23858d222213b7c278aabede763...f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6)\n\nUpdates `SonarSource/sonarqube-scan-action` from 8.2.0 to 8.2.1\n- [Release notes](https://github.com/sonarsource/sonarqube-scan-action/releases)\n- [Commits](https://github.com/sonarsource/sonarqube-scan-action/compare/713881670b6b3676cda39549040e2d88c70d582e...22918119ff8e1ca75a623e15c8296b6ea4fbe28f)\n\nUpdates `zizmorcore/zizmor-action` from 0.5.7 to 0.6.0\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/192e21d79ab29983730a13d1382995c2307fbcaa...6599ee8b7a49aef6a770f63d261d214911a7ce02)\n\n---\nupdated-dependencies:\n- dependency-name: actions/setup-node\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 8.3.2\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-go\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: dtolnay/rust-toolchain\n  dependency-version: 2c7215f132e9ebf062739d9130488b56d53c060c\n  dependency-type: direct:production\n  dependency-group: github-actions\n- dependency-name: EmbarkStudios/cargo-deny-action\n  dependency-version: 2.1.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: DavidAnson/markdownlint-cli2-action\n  dependency-version: 24.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: SonarSource/sonarqube-scan-action\n  dependency-version: 8.2.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:53:40+03:00",
          "tree_id": "57b5cb6a159a419018c14e50e110834eb13a13d7",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e261ba2563a976605c4ab10149f3e7c7fd093085"
        },
        "date": 1784638943204,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6142,
            "range": "± 93",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7135,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9924,
            "range": "± 142",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10580,
            "range": "± 140",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95914,
            "range": "± 1378",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5526,
            "range": "± 59",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6406,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8975,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9234,
            "range": "± 22",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88887,
            "range": "± 5355",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5341,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6249,
            "range": "± 60",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8571,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9023,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 87436,
            "range": "± 444",
            "unit": "ns/iter"
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
          "id": "2f2421224f4f6ba51efa5c48451477a282f20daa",
          "message": "build(deps): Bump the go-ws-hub group in /services/ws-hub with 2 updates\n\nBumps the go-ws-hub group in /services/ws-hub with 2 updates: [github.com/getsentry/sentry-go](https://github.com/getsentry/sentry-go) and [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang).\n\n\nUpdates `github.com/getsentry/sentry-go` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/prometheus/client_golang` from 1.23.2 to 1.24.0\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.0/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.23.2...v1.24.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/getsentry/sentry-go\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:54:07+03:00",
          "tree_id": "ee3394ee761ed3edd5bd8c118a69eca2a8fa096e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/2f2421224f4f6ba51efa5c48451477a282f20daa"
        },
        "date": 1784638952082,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5993,
            "range": "± 44",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6946,
            "range": "± 202",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9800,
            "range": "± 195",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10647,
            "range": "± 102",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100400,
            "range": "± 1046",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5410,
            "range": "± 57",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6338,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9048,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9432,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 92953,
            "range": "± 885",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5277,
            "range": "± 66",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6222,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8712,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9249,
            "range": "± 175",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91260,
            "range": "± 1451",
            "unit": "ns/iter"
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
          "id": "c697294c2667207f1231c2be4f2d271fdcaa5813",
          "message": "build(deps): Bump the go-gateway group in /services/gateway with 4 updates\n\nBumps the go-gateway group in /services/gateway with 4 updates: [github.com/getsentry/sentry-go](https://github.com/getsentry/sentry-go), [github.com/getsentry/sentry-go/gin](https://github.com/getsentry/sentry-go), [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/getsentry/sentry-go` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/getsentry/sentry-go/gin` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/prometheus/client_golang` from 1.23.2 to 1.24.0\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.0/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.23.2...v1.24.0)\n\nUpdates `google.golang.org/grpc` from 1.82.0 to 1.82.1\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.0...v1.82.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/getsentry/sentry-go\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/getsentry/sentry-go/gin\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.82.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:54:27+03:00",
          "tree_id": "eb1dd0533ca91270b20e7a19881a164cc4b4f6fa",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c697294c2667207f1231c2be4f2d271fdcaa5813"
        },
        "date": 1784639334600,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6222,
            "range": "± 248",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7040,
            "range": "± 380",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10105,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10862,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 103180,
            "range": "± 1615",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5416,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6405,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9220,
            "range": "± 41",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9448,
            "range": "± 36",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 95900,
            "range": "± 344",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5270,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6139,
            "range": "± 11",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8634,
            "range": "± 31",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9307,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 92931,
            "range": "± 539",
            "unit": "ns/iter"
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
          "id": "a54982147c64aeded86e81dee292376b62dcf295",
          "message": "build(deps): Bump the go-file-processor group in /services/file-processor with 3 updates\n\nBumps the go-file-processor group in /services/file-processor with 3 updates: [github.com/getsentry/sentry-go](https://github.com/getsentry/sentry-go), [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/getsentry/sentry-go` from 0.47.0 to 0.48.0\n- [Release notes](https://github.com/getsentry/sentry-go/releases)\n- [Changelog](https://github.com/getsentry/sentry-go/blob/master/CHANGELOG.md)\n- [Commits](https://github.com/getsentry/sentry-go/compare/v0.47.0...v0.48.0)\n\nUpdates `github.com/prometheus/client_golang` from 1.23.2 to 1.24.0\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.0/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.23.2...v1.24.0)\n\nUpdates `google.golang.org/grpc` from 1.82.0 to 1.82.1\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.0...v1.82.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/getsentry/sentry-go\n  dependency-version: 0.48.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.82.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-21T15:54:44+03:00",
          "tree_id": "528ee10bf2b08828be7fc5fd0474ae642ebe64b9",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a54982147c64aeded86e81dee292376b62dcf295"
        },
        "date": 1784639382779,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5978,
            "range": "± 153",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6956,
            "range": "± 73",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9881,
            "range": "± 284",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10684,
            "range": "± 65",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 99609,
            "range": "± 5878",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5340,
            "range": "± 40",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6308,
            "range": "± 19",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8990,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9385,
            "range": "± 181",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 94057,
            "range": "± 1051",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5317,
            "range": "± 64",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6274,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8614,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9203,
            "range": "± 43",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91595,
            "range": "± 750",
            "unit": "ns/iter"
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
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817422556,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 4761,
            "range": "± 166",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 5427,
            "range": "± 45",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 7670,
            "range": "± 68",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 8199,
            "range": "± 76",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 77380,
            "range": "± 1439",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 6960,
            "range": "± 79",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 7650,
            "range": "± 46",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9710,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9927,
            "range": "± 115",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 74858,
            "range": "± 238",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 4134,
            "range": "± 13",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 4852,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 6802,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 7077,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 71432,
            "range": "± 227",
            "unit": "ns/iter"
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
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191705409,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6016,
            "range": "± 147",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6932,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10066,
            "range": "± 38",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10797,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100822,
            "range": "± 451",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5387,
            "range": "± 124",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6293,
            "range": "± 87",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8974,
            "range": "± 28",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9346,
            "range": "± 127",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93022,
            "range": "± 274",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5296,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6205,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8532,
            "range": "± 133",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9234,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 91458,
            "range": "± 3052",
            "unit": "ns/iter"
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
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191854581,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6001,
            "range": "± 48",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6936,
            "range": "± 81",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10041,
            "range": "± 814",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10798,
            "range": "± 82",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 99656,
            "range": "± 1489",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5354,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6337,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9020,
            "range": "± 54",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9462,
            "range": "± 76",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 92897,
            "range": "± 578",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 7439,
            "range": "± 151",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 8301,
            "range": "± 372",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 10655,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 11266,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 93259,
            "range": "± 696",
            "unit": "ns/iter"
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
          "id": "f237c814f173127f3da824054e54268c0b13916c",
          "message": "build(deps): Bump github.com/prometheus/client_golang from 1.24.0 to 1.24.1 in /services/ws-hub in the go-ws-hub group\n\nBumps the go-ws-hub group in /services/ws-hub with 1 update: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:41:59+05:00",
          "tree_id": "79e11a838dd1d04b22410bddc066c133f55b7ee1",
          "url": "https://github.com/egorribun/university_ecosystem/commit/f237c814f173127f3da824054e54268c0b13916c"
        },
        "date": 1785862126641,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6193,
            "range": "± 118",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7116,
            "range": "± 199",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9803,
            "range": "± 101",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10413,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95227,
            "range": "± 396",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5495,
            "range": "± 109",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6412,
            "range": "± 17",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9030,
            "range": "± 34",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9244,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88981,
            "range": "± 366",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5341,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6310,
            "range": "± 49",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8569,
            "range": "± 107",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 8904,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 88106,
            "range": "± 241",
            "unit": "ns/iter"
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
          "id": "9ec989da7f5d0df782b673fb2d50d68768437f45",
          "message": "build(deps): Update fastapi requirement from <0.141,>=0.135.3 to >=0.135.3,<0.142 in the pip-dependencies group\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi) to permit the latest version.\n\nUpdates `fastapi` to 0.141.1\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.141.1)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.141.1\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:42:47+05:00",
          "tree_id": "7ec6b02cd9bfa17c94c0e69c3cedacb3f6fa15db",
          "url": "https://github.com/egorribun/university_ecosystem/commit/9ec989da7f5d0df782b673fb2d50d68768437f45"
        },
        "date": 1785862620363,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 5979,
            "range": "± 91",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 6937,
            "range": "± 270",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9888,
            "range": "± 75",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10700,
            "range": "± 39",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 100504,
            "range": "± 379",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5409,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6307,
            "range": "± 45",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9121,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9359,
            "range": "± 168",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 93064,
            "range": "± 519",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5251,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6179,
            "range": "± 63",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8625,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9201,
            "range": "± 62",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90866,
            "range": "± 990",
            "unit": "ns/iter"
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
          "id": "c2d8ff6bf96176839f211ad558dfca6d90176f0d",
          "message": "ci(deps): Bump the github-actions group with 5 updates\n\nBumps the github-actions group with 5 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.5.1` | `4.6.0` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.0` | `4.2.1` |\n\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/init` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/analyze` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `docker/login-action` from 4.5.1 to 4.6.0\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/abd2ef45e78c5afb21d64d4ca52ee8550d9572c7...dbcb813823bdd20940b903addbd779551569679f)\n\nUpdates `actions/attest` from 4.2.0 to 4.2.1\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6...508db95dd578ae2727ebd6217d5ba78e4fbda05d)\n\n---\nupdated-dependencies:\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.6.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:43:42+05:00",
          "tree_id": "d4b018610642655bc581ca575c9905429435dd0f",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c2d8ff6bf96176839f211ad558dfca6d90176f0d"
        },
        "date": 1785862885106,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6144,
            "range": "± 33",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7041,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9897,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10437,
            "range": "± 60",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95240,
            "range": "± 633",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5500,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6409,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8922,
            "range": "± 23",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9067,
            "range": "± 41",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88682,
            "range": "± 665",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5365,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6298,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8637,
            "range": "± 112",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9106,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 87783,
            "range": "± 403",
            "unit": "ns/iter"
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
          "id": "31483859811bd2cffb4671782d4d8dfeb3e9e376",
          "message": "build(deps): Bump the go-gateway group across 1 directory with 2 updates\n\nBumps the go-gateway group with 2 updates in the /services/gateway directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:44:45+05:00",
          "tree_id": "7184b30dc72715dc394cc5ddb078f2fb3fa4742d",
          "url": "https://github.com/egorribun/university_ecosystem/commit/31483859811bd2cffb4671782d4d8dfeb3e9e376"
        },
        "date": 1785862974010,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 4774,
            "range": "± 163",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 5499,
            "range": "± 25",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 7820,
            "range": "± 91",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 8235,
            "range": "± 50",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 77833,
            "range": "± 514",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 4287,
            "range": "± 32",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 4983,
            "range": "± 51",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 6967,
            "range": "± 129",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 7166,
            "range": "± 14",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 75231,
            "range": "± 767",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 4177,
            "range": "± 8",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 4944,
            "range": "± 87",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 6766,
            "range": "± 113",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 7071,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 71708,
            "range": "± 1794",
            "unit": "ns/iter"
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
          "id": "913c0db5636d6c86e28b1fc517288e551d5277ea",
          "message": "build(deps): Bump the go-file-processor group across 1 directory with 4 updates\n\nBumps the go-file-processor group with 4 updates in the /services/file-processor directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang), [go.temporal.io/api](https://github.com/temporalio/api-go), [go.temporal.io/sdk](https://github.com/temporalio/sdk-go) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `go.temporal.io/api` from 1.63.3 to 1.63.4\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.3...v1.63.4)\n\nUpdates `go.temporal.io/sdk` from 1.46.0 to 1.47.0\n- [Release notes](https://github.com/temporalio/sdk-go/releases)\n- [Changelog](https://github.com/temporalio/sdk-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/temporalio/sdk-go/compare/v1.46.0...v1.47.0)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/sdk\n  dependency-version: 1.47.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:02+05:00",
          "tree_id": "21adb758ca2821b4dc7f83d18e95b38375e28557",
          "url": "https://github.com/egorribun/university_ecosystem/commit/913c0db5636d6c86e28b1fc517288e551d5277ea"
        },
        "date": 1785863383911,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 3407,
            "range": "± 131",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 3897,
            "range": "± 87",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 5290,
            "range": "± 189",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 5678,
            "range": "± 351",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 52810,
            "range": "± 1159",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 3092,
            "range": "± 73",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 3406,
            "range": "± 58",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 4874,
            "range": "± 130",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 4991,
            "range": "± 254",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 49176,
            "range": "± 1963",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 3001,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 3536,
            "range": "± 554",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 4722,
            "range": "± 144",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 4907,
            "range": "± 207",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 47880,
            "range": "± 1138",
            "unit": "ns/iter"
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
          "id": "4d8fcde61831ab6443e1f8dbfa86e644e3c28809",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [msgpack](https://github.com/msgpack/msgpack-python) and [pip](https://github.com/pypa/pip).\n\n\nUpdates `msgpack` from 1.1.2 to 1.2.1\n- [Release notes](https://github.com/msgpack/msgpack-python/releases)\n- [Changelog](https://github.com/msgpack/msgpack-python/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/msgpack/msgpack-python/compare/v1.1.2...v1.2.1)\n\nUpdates `pip` from 26.1 to 26.1.2\n- [Changelog](https://github.com/pypa/pip/blob/main/NEWS.rst)\n- [Commits](https://github.com/pypa/pip/compare/26.1...26.1.2)\n\n---\nupdated-dependencies:\n- dependency-name: msgpack\n  dependency-version: 1.2.1\n  dependency-type: indirect\n  dependency-group: uv\n- dependency-name: pip\n  dependency-version: 26.1.2\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:28+05:00",
          "tree_id": "d8c3204dc26f383bcbfda522958a3b9258229d5e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/4d8fcde61831ab6443e1f8dbfa86e644e3c28809"
        },
        "date": 1785863636147,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6129,
            "range": "± 56",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7103,
            "range": "± 69",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9964,
            "range": "± 25",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10474,
            "range": "± 30",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 98747,
            "range": "± 4673",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5583,
            "range": "± 16",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6483,
            "range": "± 138",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 9072,
            "range": "± 24",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9297,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 90746,
            "range": "± 722",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5318,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6272,
            "range": "± 94",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8598,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9136,
            "range": "± 39",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 90298,
            "range": "± 2913",
            "unit": "ns/iter"
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
          "id": "dd9c6405161d8ec6c5bc34bd617712f667abe2d5",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [pyasn1](https://github.com/pyasn1/pyasn1) and [aiohttp](https://github.com/aio-libs/aiohttp).\n\n\nUpdates `pyasn1` from 0.6.3 to 0.6.4\n- [Release notes](https://github.com/pyasn1/pyasn1/releases)\n- [Changelog](https://github.com/pyasn1/pyasn1/blob/main/CHANGES.rst)\n- [Commits](https://github.com/pyasn1/pyasn1/compare/v0.6.3...v0.6.4)\n\nUpdates `aiohttp` from 3.14.1 to 3.14.3\n- [Changelog](https://github.com/aio-libs/aiohttp/blob/master/CHANGES.rst)\n- [Commits](https://github.com/aio-libs/aiohttp/compare/v3.14.1...v3.14.3)\n\n---\nupdated-dependencies:\n- dependency-name: pyasn1\n  dependency-version: 0.6.4\n  dependency-type: direct:production\n  dependency-group: uv\n- dependency-name: aiohttp\n  dependency-version: 3.14.3\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-05T00:36:25+05:00",
          "tree_id": "4af11d38f9b1dc1eacfe0e5b24369e5b9f8c65b7",
          "url": "https://github.com/egorribun/university_ecosystem/commit/dd9c6405161d8ec6c5bc34bd617712f667abe2d5"
        },
        "date": 1785872421603,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6137,
            "range": "± 90",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7079,
            "range": "± 144",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 10000,
            "range": "± 39",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10546,
            "range": "± 125",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 96349,
            "range": "± 596",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5397,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6361,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8869,
            "range": "± 31",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9211,
            "range": "± 67",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 88872,
            "range": "± 2178",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5317,
            "range": "± 85",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6304,
            "range": "± 21",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8615,
            "range": "± 20",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9061,
            "range": "± 99",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 86856,
            "range": "± 507",
            "unit": "ns/iter"
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
          "id": "59a94734bf71377c8f83f1b486ae1f44d7a97070",
          "message": "ci(deps): Bump the npm_and_yarn group across 2 directories with 13 updates (#1226)\n\nBumps the npm_and_yarn group with 4 updates in the / directory: [undici](https://github.com/nodejs/undici), [handlebars](https://github.com/handlebars-lang/handlebars.js), [lodash](https://github.com/lodash/lodash) and [minimatch](https://github.com/isaacs/minimatch).\nBumps the npm_and_yarn group with 7 updates in the /frontend directory:\n\n| Package | From | To |\n| --- | --- | --- |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `5.0.7` | `5.0.9` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `2.1.2` | `2.1.4` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `1.1.16` | `1.1.18` |\n| [ip-address](https://github.com/beaugunderson/ip-address) | `10.2.0` | `10.4.0` |\n| [@vitest/browser](https://github.com/vitest-dev/vitest/tree/HEAD/packages/browser) | `3.2.6` | `4.1.10` |\n| [postcss](https://github.com/postcss/postcss) | `8.5.16` | `8.5.25` |\n| [sharp](https://github.com/lovell/sharp) | `0.34.5` | `0.35.0` |\n| [dompurify](https://github.com/cure53/DOMPurify) | `3.4.11` | `3.4.13` |\n| [fast-uri](https://github.com/fastify/fast-uri) | `3.1.2` | `3.1.5` |\n\n\n\nUpdates `undici` from 6.23.0 to 6.28.0\n- [Release notes](https://github.com/nodejs/undici/releases)\n- [Commits](https://github.com/nodejs/undici/compare/v6.23.0...v6.28.0)\n\nUpdates `handlebars` from 4.7.8 to 4.7.9\n- [Release notes](https://github.com/handlebars-lang/handlebars.js/releases)\n- [Changelog](https://github.com/handlebars-lang/handlebars.js/blob/v4.7.9/release-notes.md)\n- [Commits](https://github.com/handlebars-lang/handlebars.js/compare/v4.7.8...v4.7.9)\n\nUpdates `lodash` from 4.17.23 to 4.18.1\n- [Release notes](https://github.com/lodash/lodash/releases)\n- [Commits](https://github.com/lodash/lodash/compare/4.17.23...4.18.1)\n\nUpdates `minimatch` from 10.2.2 to 10.2.5\n- [Changelog](https://github.com/isaacs/minimatch/blob/main/changelog.md)\n- [Commits](https://github.com/isaacs/minimatch/compare/v10.2.2...v10.2.5)\n\nUpdates `sigstore` from 4.1.0 to 4.1.1\n- [Release notes](https://github.com/sigstore/sigstore-js/releases)\n- [Commits](https://github.com/sigstore/sigstore-js/compare/sigstore@4.1.0...sigstore@4.1.1)\n\nUpdates `tar` from 7.5.9 to 7.5.19\n- [Release notes](https://github.com/isaacs/node-tar/releases)\n- [Changelog](https://github.com/isaacs/node-tar/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/isaacs/node-tar/compare/v7.5.9...v7.5.19)\n\nUpdates `brace-expansion` from 5.0.7 to 5.0.9\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 2.1.2 to 2.1.4\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 1.1.16 to 1.1.18\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `ip-address` from 10.2.0 to 10.4.0\n- [Release notes](https://github.com/beaugunderson/ip-address/releases)\n- [Commits](https://github.com/beaugunderson/ip-address/compare/v10.2.0...v10.4.0)\n\nUpdates `@vitest/browser` from 3.2.6 to 4.1.10\n- [Release notes](https://github.com/vitest-dev/vitest/releases)\n- [Changelog](https://github.com/vitest-dev/vitest/blob/main/docs/releases.md)\n- [Commits](https://github.com/vitest-dev/vitest/commits/v4.1.10/packages/browser)\n\nUpdates `postcss` from 8.5.16 to 8.5.25\n- [Release notes](https://github.com/postcss/postcss/releases)\n- [Changelog](https://github.com/postcss/postcss/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/postcss/postcss/compare/8.5.16...8.5.25)\n\nUpdates `sharp` from 0.34.5 to 0.35.0\n- [Release notes](https://github.com/lovell/sharp/releases)\n- [Commits](https://github.com/lovell/sharp/compare/v0.34.5...v0.35.0)\n\nUpdates `dompurify` from 3.4.11 to 3.4.13\n- [Release notes](https://github.com/cure53/DOMPurify/releases)\n- [Commits](https://github.com/cure53/DOMPurify/compare/3.4.11...3.4.13)\n\nUpdates `fast-uri` from 3.1.2 to 3.1.5\n- [Release notes](https://github.com/fastify/fast-uri/releases)\n- [Commits](https://github.com/fastify/fast-uri/compare/v3.1.2...v3.1.5)\n\n---\nupdated-dependencies:\n- dependency-name: undici\n  dependency-version: 6.28.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: handlebars\n  dependency-version: 4.7.9\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: lodash\n  dependency-version: 4.18.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: minimatch\n  dependency-version: 10.2.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: sigstore\n  dependency-version: 4.1.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: tar\n  dependency-version: 7.5.19\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 5.0.9\n  dependency-type: direct:production\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 2.1.4\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 1.1.18\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: ip-address\n  dependency-version: 10.4.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: \"@vitest/browser\"\n  dependency-version: 4.1.10\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: postcss\n  dependency-version: 8.5.25\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: sharp\n  dependency-version: 0.35.0\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: dompurify\n  dependency-version: 3.4.13\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: fast-uri\n  dependency-version: 3.1.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T23:16:53+03:00",
          "tree_id": "358d295e79f3adb3f6a4dbcc1688157540dcc98a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/59a94734bf71377c8f83f1b486ae1f44d7a97070"
        },
        "date": 1785874849157,
        "tool": "cargo",
        "benches": [
          {
            "name": "sanitize_rich_text/empty",
            "value": 6139,
            "range": "± 192",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/plain_text",
            "value": 7027,
            "range": "± 15",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/simple_html",
            "value": 9886,
            "range": "± 78",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/xss_attempt",
            "value": 10527,
            "range": "± 435",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_rich_text/large",
            "value": 95258,
            "range": "± 1454",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/empty",
            "value": 5512,
            "range": "± 29",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/plain_text",
            "value": 6383,
            "range": "± 26",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/simple_html",
            "value": 8916,
            "range": "± 178",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/xss_attempt",
            "value": 9214,
            "range": "± 35",
            "unit": "ns/iter"
          },
          {
            "name": "sanitize_html_basic/large",
            "value": 87586,
            "range": "± 821",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/empty",
            "value": 5351,
            "range": "± 77",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/plain_text",
            "value": 6295,
            "range": "± 18",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/simple_html",
            "value": 8556,
            "range": "± 64",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/xss_attempt",
            "value": 9047,
            "range": "± 120",
            "unit": "ns/iter"
          },
          {
            "name": "strip_html/large",
            "value": 85917,
            "range": "± 625",
            "unit": "ns/iter"
          }
        ]
      }
    ],
    "Rust Native Optimizer Regression Gate": [
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
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817311996,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 10203,
            "range": "± 289",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 28533,
            "range": "± 640",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 47517,
            "range": "± 1379",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 257463,
            "range": "± 7021",
            "unit": "ns/iter"
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
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191545222,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 10711,
            "range": "± 585",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 18552,
            "range": "± 676",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 30807,
            "range": "± 909",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 260262,
            "range": "± 8911",
            "unit": "ns/iter"
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
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191600606,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13302,
            "range": "± 337",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22665,
            "range": "± 1083",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39566,
            "range": "± 3707",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 341535,
            "range": "± 10437",
            "unit": "ns/iter"
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
          "id": "f237c814f173127f3da824054e54268c0b13916c",
          "message": "build(deps): Bump github.com/prometheus/client_golang from 1.24.0 to 1.24.1 in /services/ws-hub in the go-ws-hub group\n\nBumps the go-ws-hub group in /services/ws-hub with 1 update: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-ws-hub\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:41:59+05:00",
          "tree_id": "79e11a838dd1d04b22410bddc066c133f55b7ee1",
          "url": "https://github.com/egorribun/university_ecosystem/commit/f237c814f173127f3da824054e54268c0b13916c"
        },
        "date": 1785861990405,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13543,
            "range": "± 298",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22750,
            "range": "± 2395",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39183,
            "range": "± 1194",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 339244,
            "range": "± 8332",
            "unit": "ns/iter"
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
          "id": "9ec989da7f5d0df782b673fb2d50d68768437f45",
          "message": "build(deps): Update fastapi requirement from <0.141,>=0.135.3 to >=0.135.3,<0.142 in the pip-dependencies group\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi) to permit the latest version.\n\nUpdates `fastapi` to 0.141.1\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.141.1)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.141.1\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:42:47+05:00",
          "tree_id": "7ec6b02cd9bfa17c94c0e69c3cedacb3f6fa15db",
          "url": "https://github.com/egorribun/university_ecosystem/commit/9ec989da7f5d0df782b673fb2d50d68768437f45"
        },
        "date": 1785862077308,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13593,
            "range": "± 945",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22649,
            "range": "± 478",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 40298,
            "range": "± 2204",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 344970,
            "range": "± 9628",
            "unit": "ns/iter"
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
          "id": "c2d8ff6bf96176839f211ad558dfca6d90176f0d",
          "message": "ci(deps): Bump the github-actions group with 5 updates\n\nBumps the github-actions group with 5 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.3` | `4.37.4` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.5.1` | `4.6.0` |\n| [actions/attest](https://github.com/actions/attest) | `4.2.0` | `4.2.1` |\n\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/init` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `github/codeql-action/analyze` from 4.37.3 to 4.37.4\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81...f205ea1c3313d32999d8d6a48b4f6530d4437b38)\n\nUpdates `docker/login-action` from 4.5.1 to 4.6.0\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/abd2ef45e78c5afb21d64d4ca52ee8550d9572c7...dbcb813823bdd20940b903addbd779551569679f)\n\nUpdates `actions/attest` from 4.2.0 to 4.2.1\n- [Release notes](https://github.com/actions/attest/releases)\n- [Changelog](https://github.com/actions/attest/blob/main/RELEASE.md)\n- [Commits](https://github.com/actions/attest/compare/f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6...508db95dd578ae2727ebd6217d5ba78e4fbda05d)\n\n---\nupdated-dependencies:\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.6.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: actions/attest\n  dependency-version: 4.2.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:43:42+05:00",
          "tree_id": "d4b018610642655bc581ca575c9905429435dd0f",
          "url": "https://github.com/egorribun/university_ecosystem/commit/c2d8ff6bf96176839f211ad558dfca6d90176f0d"
        },
        "date": 1785862648329,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13438,
            "range": "± 564",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22791,
            "range": "± 2884",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39701,
            "range": "± 1301",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 341797,
            "range": "± 9477",
            "unit": "ns/iter"
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
          "id": "31483859811bd2cffb4671782d4d8dfeb3e9e376",
          "message": "build(deps): Bump the go-gateway group across 1 directory with 2 updates\n\nBumps the go-gateway group with 2 updates in the /services/gateway directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-gateway\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-gateway\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:44:45+05:00",
          "tree_id": "7184b30dc72715dc394cc5ddb078f2fb3fa4742d",
          "url": "https://github.com/egorribun/university_ecosystem/commit/31483859811bd2cffb4671782d4d8dfeb3e9e376"
        },
        "date": 1785863089006,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13876,
            "range": "± 471",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 24321,
            "range": "± 1187",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 40663,
            "range": "± 1567",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 342813,
            "range": "± 15908",
            "unit": "ns/iter"
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
          "id": "913c0db5636d6c86e28b1fc517288e551d5277ea",
          "message": "build(deps): Bump the go-file-processor group across 1 directory with 4 updates\n\nBumps the go-file-processor group with 4 updates in the /services/file-processor directory: [github.com/prometheus/client_golang](https://github.com/prometheus/client_golang), [go.temporal.io/api](https://github.com/temporalio/api-go), [go.temporal.io/sdk](https://github.com/temporalio/sdk-go) and [google.golang.org/grpc](https://github.com/grpc/grpc-go).\n\n\nUpdates `github.com/prometheus/client_golang` from 1.24.0 to 1.24.1\n- [Release notes](https://github.com/prometheus/client_golang/releases)\n- [Changelog](https://github.com/prometheus/client_golang/blob/v1.24.1/CHANGELOG.md)\n- [Commits](https://github.com/prometheus/client_golang/compare/v1.24.0...v1.24.1)\n\nUpdates `go.temporal.io/api` from 1.63.3 to 1.63.4\n- [Release notes](https://github.com/temporalio/api-go/releases)\n- [Commits](https://github.com/temporalio/api-go/compare/v1.63.3...v1.63.4)\n\nUpdates `go.temporal.io/sdk` from 1.46.0 to 1.47.0\n- [Release notes](https://github.com/temporalio/sdk-go/releases)\n- [Changelog](https://github.com/temporalio/sdk-go/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/temporalio/sdk-go/compare/v1.46.0...v1.47.0)\n\nUpdates `google.golang.org/grpc` from 1.82.1 to 1.83.0\n- [Release notes](https://github.com/grpc/grpc-go/releases)\n- [Commits](https://github.com/grpc/grpc-go/compare/v1.82.1...v1.83.0)\n\n---\nupdated-dependencies:\n- dependency-name: github.com/prometheus/client_golang\n  dependency-version: 1.24.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/api\n  dependency-version: 1.63.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: go-file-processor\n- dependency-name: go.temporal.io/sdk\n  dependency-version: 1.47.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n- dependency-name: google.golang.org/grpc\n  dependency-version: 1.83.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: go-file-processor\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:02+05:00",
          "tree_id": "21adb758ca2821b4dc7f83d18e95b38375e28557",
          "url": "https://github.com/egorribun/university_ecosystem/commit/913c0db5636d6c86e28b1fc517288e551d5277ea"
        },
        "date": 1785863222176,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13484,
            "range": "± 685",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22602,
            "range": "± 1113",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 38995,
            "range": "± 1727",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 338849,
            "range": "± 9007",
            "unit": "ns/iter"
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
          "id": "4d8fcde61831ab6443e1f8dbfa86e644e3c28809",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [msgpack](https://github.com/msgpack/msgpack-python) and [pip](https://github.com/pypa/pip).\n\n\nUpdates `msgpack` from 1.1.2 to 1.2.1\n- [Release notes](https://github.com/msgpack/msgpack-python/releases)\n- [Changelog](https://github.com/msgpack/msgpack-python/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/msgpack/msgpack-python/compare/v1.1.2...v1.2.1)\n\nUpdates `pip` from 26.1 to 26.1.2\n- [Changelog](https://github.com/pypa/pip/blob/main/NEWS.rst)\n- [Commits](https://github.com/pypa/pip/compare/26.1...26.1.2)\n\n---\nupdated-dependencies:\n- dependency-name: msgpack\n  dependency-version: 1.2.1\n  dependency-type: indirect\n  dependency-group: uv\n- dependency-name: pip\n  dependency-version: 26.1.2\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T21:45:28+05:00",
          "tree_id": "d8c3204dc26f383bcbfda522958a3b9258229d5e",
          "url": "https://github.com/egorribun/university_ecosystem/commit/4d8fcde61831ab6443e1f8dbfa86e644e3c28809"
        },
        "date": 1785863462831,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13430,
            "range": "± 438",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22837,
            "range": "± 1346",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39823,
            "range": "± 2066",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 346984,
            "range": "± 10057",
            "unit": "ns/iter"
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
          "id": "dd9c6405161d8ec6c5bc34bd617712f667abe2d5",
          "message": "ci(deps): Bump the uv group across 1 directory with 2 updates\n\nBumps the uv group with 2 updates in the / directory: [pyasn1](https://github.com/pyasn1/pyasn1) and [aiohttp](https://github.com/aio-libs/aiohttp).\n\n\nUpdates `pyasn1` from 0.6.3 to 0.6.4\n- [Release notes](https://github.com/pyasn1/pyasn1/releases)\n- [Changelog](https://github.com/pyasn1/pyasn1/blob/main/CHANGES.rst)\n- [Commits](https://github.com/pyasn1/pyasn1/compare/v0.6.3...v0.6.4)\n\nUpdates `aiohttp` from 3.14.1 to 3.14.3\n- [Changelog](https://github.com/aio-libs/aiohttp/blob/master/CHANGES.rst)\n- [Commits](https://github.com/aio-libs/aiohttp/compare/v3.14.1...v3.14.3)\n\n---\nupdated-dependencies:\n- dependency-name: pyasn1\n  dependency-version: 0.6.4\n  dependency-type: direct:production\n  dependency-group: uv\n- dependency-name: aiohttp\n  dependency-version: 3.14.3\n  dependency-type: indirect\n  dependency-group: uv\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-05T00:36:25+05:00",
          "tree_id": "4af11d38f9b1dc1eacfe0e5b24369e5b9f8c65b7",
          "url": "https://github.com/egorribun/university_ecosystem/commit/dd9c6405161d8ec6c5bc34bd617712f667abe2d5"
        },
        "date": 1785872270941,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 13452,
            "range": "± 663",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22687,
            "range": "± 714",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 39568,
            "range": "± 4399",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 339755,
            "range": "± 6213",
            "unit": "ns/iter"
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
          "id": "59a94734bf71377c8f83f1b486ae1f44d7a97070",
          "message": "ci(deps): Bump the npm_and_yarn group across 2 directories with 13 updates (#1226)\n\nBumps the npm_and_yarn group with 4 updates in the / directory: [undici](https://github.com/nodejs/undici), [handlebars](https://github.com/handlebars-lang/handlebars.js), [lodash](https://github.com/lodash/lodash) and [minimatch](https://github.com/isaacs/minimatch).\nBumps the npm_and_yarn group with 7 updates in the /frontend directory:\n\n| Package | From | To |\n| --- | --- | --- |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `5.0.7` | `5.0.9` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `2.1.2` | `2.1.4` |\n| [brace-expansion](https://github.com/juliangruber/brace-expansion) | `1.1.16` | `1.1.18` |\n| [ip-address](https://github.com/beaugunderson/ip-address) | `10.2.0` | `10.4.0` |\n| [@vitest/browser](https://github.com/vitest-dev/vitest/tree/HEAD/packages/browser) | `3.2.6` | `4.1.10` |\n| [postcss](https://github.com/postcss/postcss) | `8.5.16` | `8.5.25` |\n| [sharp](https://github.com/lovell/sharp) | `0.34.5` | `0.35.0` |\n| [dompurify](https://github.com/cure53/DOMPurify) | `3.4.11` | `3.4.13` |\n| [fast-uri](https://github.com/fastify/fast-uri) | `3.1.2` | `3.1.5` |\n\n\n\nUpdates `undici` from 6.23.0 to 6.28.0\n- [Release notes](https://github.com/nodejs/undici/releases)\n- [Commits](https://github.com/nodejs/undici/compare/v6.23.0...v6.28.0)\n\nUpdates `handlebars` from 4.7.8 to 4.7.9\n- [Release notes](https://github.com/handlebars-lang/handlebars.js/releases)\n- [Changelog](https://github.com/handlebars-lang/handlebars.js/blob/v4.7.9/release-notes.md)\n- [Commits](https://github.com/handlebars-lang/handlebars.js/compare/v4.7.8...v4.7.9)\n\nUpdates `lodash` from 4.17.23 to 4.18.1\n- [Release notes](https://github.com/lodash/lodash/releases)\n- [Commits](https://github.com/lodash/lodash/compare/4.17.23...4.18.1)\n\nUpdates `minimatch` from 10.2.2 to 10.2.5\n- [Changelog](https://github.com/isaacs/minimatch/blob/main/changelog.md)\n- [Commits](https://github.com/isaacs/minimatch/compare/v10.2.2...v10.2.5)\n\nUpdates `sigstore` from 4.1.0 to 4.1.1\n- [Release notes](https://github.com/sigstore/sigstore-js/releases)\n- [Commits](https://github.com/sigstore/sigstore-js/compare/sigstore@4.1.0...sigstore@4.1.1)\n\nUpdates `tar` from 7.5.9 to 7.5.19\n- [Release notes](https://github.com/isaacs/node-tar/releases)\n- [Changelog](https://github.com/isaacs/node-tar/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/isaacs/node-tar/compare/v7.5.9...v7.5.19)\n\nUpdates `brace-expansion` from 5.0.7 to 5.0.9\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 2.1.2 to 2.1.4\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `brace-expansion` from 1.1.16 to 1.1.18\n- [Release notes](https://github.com/juliangruber/brace-expansion/releases)\n- [Commits](https://github.com/juliangruber/brace-expansion/compare/v5.0.7...v5.0.9)\n\nUpdates `ip-address` from 10.2.0 to 10.4.0\n- [Release notes](https://github.com/beaugunderson/ip-address/releases)\n- [Commits](https://github.com/beaugunderson/ip-address/compare/v10.2.0...v10.4.0)\n\nUpdates `@vitest/browser` from 3.2.6 to 4.1.10\n- [Release notes](https://github.com/vitest-dev/vitest/releases)\n- [Changelog](https://github.com/vitest-dev/vitest/blob/main/docs/releases.md)\n- [Commits](https://github.com/vitest-dev/vitest/commits/v4.1.10/packages/browser)\n\nUpdates `postcss` from 8.5.16 to 8.5.25\n- [Release notes](https://github.com/postcss/postcss/releases)\n- [Changelog](https://github.com/postcss/postcss/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/postcss/postcss/compare/8.5.16...8.5.25)\n\nUpdates `sharp` from 0.34.5 to 0.35.0\n- [Release notes](https://github.com/lovell/sharp/releases)\n- [Commits](https://github.com/lovell/sharp/compare/v0.34.5...v0.35.0)\n\nUpdates `dompurify` from 3.4.11 to 3.4.13\n- [Release notes](https://github.com/cure53/DOMPurify/releases)\n- [Commits](https://github.com/cure53/DOMPurify/compare/3.4.11...3.4.13)\n\nUpdates `fast-uri` from 3.1.2 to 3.1.5\n- [Release notes](https://github.com/fastify/fast-uri/releases)\n- [Commits](https://github.com/fastify/fast-uri/compare/v3.1.2...v3.1.5)\n\n---\nupdated-dependencies:\n- dependency-name: undici\n  dependency-version: 6.28.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: handlebars\n  dependency-version: 4.7.9\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: lodash\n  dependency-version: 4.18.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: minimatch\n  dependency-version: 10.2.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: sigstore\n  dependency-version: 4.1.1\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: tar\n  dependency-version: 7.5.19\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 5.0.9\n  dependency-type: direct:production\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 2.1.4\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: brace-expansion\n  dependency-version: 1.1.18\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: ip-address\n  dependency-version: 10.4.0\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: \"@vitest/browser\"\n  dependency-version: 4.1.10\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: postcss\n  dependency-version: 8.5.25\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: sharp\n  dependency-version: 0.35.0\n  dependency-type: direct:development\n  dependency-group: npm_and_yarn\n- dependency-name: dompurify\n  dependency-version: 3.4.13\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n- dependency-name: fast-uri\n  dependency-version: 3.1.5\n  dependency-type: indirect\n  dependency-group: npm_and_yarn\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-08-04T23:16:53+03:00",
          "tree_id": "358d295e79f3adb3f6a4dbcc1688157540dcc98a",
          "url": "https://github.com/egorribun/university_ecosystem/commit/59a94734bf71377c8f83f1b486ae1f44d7a97070"
        },
        "date": 1785874695984,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 11131,
            "range": "± 445",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 31300,
            "range": "± 733",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 54181,
            "range": "± 1102",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 303425,
            "range": "± 8731",
            "unit": "ns/iter"
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
          "id": "496ed7f2c5c0fd33da738b4687b4c31281f14d7e",
          "message": "fix(ci): restore checks after draft pull requests become ready (#1227)\n\n* feat(wave212): remove obsolete handoff prompt\n\n* fix(ci): trigger checks when draft PR becomes ready\n\n* test(quality): cover gateway TLS certificate failure paths\n\n* fix(ci): keep required OpenAPI check live on every PR\n\n* fix(ci): run frontend mutation gate during manual recovery\n\n* test(gateway): satisfy Go lint and nil analysis\n\n* fix(ci): add manual recovery triggers for Go analysis\n\n* fix(ci): make gosec test directive effective\n\n* fix(ci): use canonical lighthouse assertions\n\n* fix(ci): eliminate ws-hub shutdown race\n\n* fix(ci): handle ws-hub socket cleanup error\n\n* fix(ci): reduce ws-hub server complexity\n\n* fix(ci): align lighthouse gates with canonical config\n\n* fix(ci): isolate backend integration test scope\n\n* fix(ci): start minio for chaos services\n\n* fix(quality): consume frontend statement coverage\n\n* fix(ci): close PR check and coverage gaps\n\n* fix(ci): close analyzer findings\n\n* fix(ci): drain file processor servers before return\n\n* fix(ci): close coverage gate deficits\n\n* fix(ci): make PR quality gate reproducible\n\n* fix(ci): prevent security scan alert drift\n\n* fix(ci): retry testcontainer image pulls\n\n* fix(ci): stabilize browser e2e execution\n\n* fix(ci): close mutation and tier0 coverage gaps\n\n* fix(ci): unblock code scanning ruleset\n\n* fix(ci): preserve scoped trivy suppressions\n\n* fix(ci): filter suppressed checkov alerts\n\n* fix(ci): write filtered checkov sarif separately\n\n* fix(ci): use one trivy ignore format\n\n* fix(ci): make Semgrep SARIF analysis reliable\n\n* fix(ci): make Semgrep pull requests diff-aware\n\n* fix(ci): close Semgrep findings in integration gate\n\n* fix(ci): make gateway race performance gate stable\n\n* fix(ci): remove golangci schema network dependency\n\n* fix(ci): avoid redundant Lighthouse dependency bootstrap\n\n* fix(ci): close session crypto coverage branch\n\n* fix(ci): include workflow contract inputs in mutmut sandbox\n\n* fix(test): bound Miri sanitizer payload\n\n* fix(test): reduce Miri sanitizer fixture\n\n* fix(test): invalidate cached JWT keys on rotation\n\n* fix(test): isolate notification metrics state\n\n* chore: update codebase test coverage reports and configuration files\n\n* fix(ci): balance incremental mutmut shards\n\n* fix(test): clean up SPIFFE stress test lint\n\n* fix(test): isolate ChatWindow render suites\n\n* fix(frontend): guard profile sync auto-fetch reruns\n\n* fix(test): isolate profile coverage suites\n\n* fix(test): isolate component coverage suites\n\n* fix(test): isolate event hero coverage suites\n\n* fix(test): isolate schedule and event file suites\n\n* chore(test): checkpoint current branch changes\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>",
          "timestamp": "2026-08-08T21:40:49+03:00",
          "tree_id": "26101b1ba5348abe8e9c0a22c539a733d8f96e1b",
          "url": "https://github.com/egorribun/university_ecosystem/commit/496ed7f2c5c0fd33da738b4687b4c31281f14d7e"
        },
        "date": 1786214795987,
        "tool": "cargo",
        "benches": [
          {
            "name": "batch_detect_conflicts/10",
            "value": 679,
            "range": "± 7",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/50",
            "value": 22838,
            "range": "± 4298",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/100",
            "value": 35952,
            "range": "± 1595",
            "unit": "ns/iter"
          },
          {
            "name": "batch_detect_conflicts/500",
            "value": 236883,
            "range": "± 6601",
            "unit": "ns/iter"
          }
        ]
      }
    ],
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
          "id": "a9b871378c3e5d4413c7bb60c74890a9a97eca51",
          "message": "update\n\n* feat(opencode): add 154 agent skills\n\n* fix(alembic): adjust notification_deliveries FK for SQLite compatibility\n\n* feat(wave100): harden quality governance gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): close checkov baseline findings\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* fix(wave100): narrow checkov exceptions\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add full quality gate and Tier0 evidence\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce mutation gate and add stateful tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add frontend property and mutation gates\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave100): lock frontend gate workflow contract\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* feat(wave100): close rust coverage and fuzz contracts\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): enforce kyverno policy tests\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): add lifecycle certification and fuzz gates\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave100): close rust native coverage contract\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* feat(wave101): close contract replay and compatibility gates\n\n* feat(wave102): close quality evidence and integration gates\n\nCo-Authored-By: Codex <noreply@openai.com>\n\n* feat(wave103): validate equivalent mutation registry\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave104): close GraphQL auth validator branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave105): cover login session fallback branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave106): close lockout policy branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave107): close security tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave108): close login route tier0 branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave109): close metrics coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave110): close observability coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave111): close cache backend coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave112): close presence coverage branches\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave113): close notification settings coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave114): close connection manager coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave115): close Spotify API coverage\n\nCo-Authored-By: Codex <codex@openai.com>\n\n* test(wave116): close notifications API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave117): close Events API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test(wave118): close Users API coverage\n\nCo-Authored-By: OpenAI <noreply@openai.com>\n\n* test: add comprehensive test closure suite and quality roadmap plan\n\n* docs: align README, CONTRIBUTING, and SECURITY policies\n\n---------\n\nCo-authored-by: Egor Ribun <egorribun@gmail.com>\nCo-authored-by: Codex <codex@openai.com>\nCo-authored-by: OpenAI <noreply@openai.com>",
          "timestamp": "2026-07-23T17:28:41+03:00",
          "tree_id": "3496dd2331c34c7fe374a9b4fde4495d07a2aee6",
          "url": "https://github.com/egorribun/university_ecosystem/commit/a9b871378c3e5d4413c7bb60c74890a9a97eca51"
        },
        "date": 1784817387510,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 596.8,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 596.8,
            "unit": "ns/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2015131 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 599.4,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 599.4,
            "unit": "ns/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1983704 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 604,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 604,
            "unit": "ns/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2004056 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 598.4,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 598.4,
            "unit": "ns/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1988410 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 593.7,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 593.7,
            "unit": "ns/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2012065 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1545,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1545,
            "unit": "ns/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "764361 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1558,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1558,
            "unit": "ns/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "763803 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1542,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1542,
            "unit": "ns/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "748497 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1547,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1547,
            "unit": "ns/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "773904 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1537,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1537,
            "unit": "ns/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "739971 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.82,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.82,
            "unit": "ns/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86745158 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.86,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.86,
            "unit": "ns/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86234160 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.79,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.79,
            "unit": "ns/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "82128394 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.78,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.78,
            "unit": "ns/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86997606 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.99,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.99,
            "unit": "ns/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "87095274 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 793.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 793.9,
            "unit": "ns/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1552398 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 796,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 796,
            "unit": "ns/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1528304 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 782.1,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 782.1,
            "unit": "ns/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1500562 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 782.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 782.9,
            "unit": "ns/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1560156 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 778.5,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 778.5,
            "unit": "ns/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1599548 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 90.42,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 90.42,
            "unit": "ns/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12100154 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 90.89,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 90.89,
            "unit": "ns/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12832407 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 91.17,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 91.17,
            "unit": "ns/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12321854 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 93.89,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 93.89,
            "unit": "ns/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12017438 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 92.58,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 92.58,
            "unit": "ns/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12982334 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1424,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1424,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1393,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1393,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1421,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1421,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1418,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1418,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1428,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1428,
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
            "value": 53.12,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 53.12,
            "unit": "ns/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "24244844 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 48.64,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 48.64,
            "unit": "ns/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25454995 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 47.34,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 47.34,
            "unit": "ns/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25626093 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 46.98,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 46.98,
            "unit": "ns/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25554176 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 48.35,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 48.35,
            "unit": "ns/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "22098645 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1995,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1995,
            "unit": "ns/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "654016 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1600,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1600,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1654,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1654,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1632,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1632,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1757,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1757,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "value": 64.79,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.79,
            "unit": "ns/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18846784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 65.27,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 65.27,
            "unit": "ns/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18482647 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 63.89,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 63.89,
            "unit": "ns/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18410550 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 64.32,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.32,
            "unit": "ns/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18753894 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 64.12,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.12,
            "unit": "ns/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18875784 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 693.3,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 693.3,
            "unit": "ns/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1708978 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 695.4,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 695.4,
            "unit": "ns/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1724782 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 704.7,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 704.7,
            "unit": "ns/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1702286 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 704.9,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 704.9,
            "unit": "ns/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1698588 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 711.1,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 711.1,
            "unit": "ns/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1683704 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 13021,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 13021,
            "unit": "ns/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "92463 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12995,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12995,
            "unit": "ns/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "94566 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12764,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12764,
            "unit": "ns/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93675 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12903,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12903,
            "unit": "ns/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "91497 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12964,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "92793 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12964,
            "unit": "ns/op",
            "extra": "92793 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "92793 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "92793 times\n4 procs"
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
          "id": "7f1fc19ce7e10fa0c33e4af8953eca343e5b9922",
          "message": "build(deps): Bump the pip-dependencies group with 3 updates\n\nUpdates the requirements on [fastapi](https://github.com/fastapi/fastapi), [strawberry-graphql](https://github.com/sponsors/strawberry-graphql) and [ruff](https://github.com/astral-sh/ruff) to permit the latest version.\n\nUpdates `fastapi` to 0.140.0\n- [Release notes](https://github.com/fastapi/fastapi/releases)\n- [Commits](https://github.com/fastapi/fastapi/compare/0.135.3...0.140.0)\n\nUpdates `strawberry-graphql` to 0.323.2\n- [Commits](https://github.com/sponsors/strawberry-graphql/commits)\n\nUpdates `ruff` to 0.16.0\n- [Release notes](https://github.com/astral-sh/ruff/releases)\n- [Changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/astral-sh/ruff/compare/0.14.14...0.16.0)\n\n---\nupdated-dependencies:\n- dependency-name: fastapi\n  dependency-version: 0.140.0\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: strawberry-graphql\n  dependency-version: 0.323.2\n  dependency-type: direct:production\n  dependency-group: pip-dependencies\n- dependency-name: ruff\n  dependency-version: 0.16.0\n  dependency-type: direct:development\n  dependency-group: pip-dependencies\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:17+03:00",
          "tree_id": "62034fe5aca14f638987f0da125997f2063dc5cc",
          "url": "https://github.com/egorribun/university_ecosystem/commit/7f1fc19ce7e10fa0c33e4af8953eca343e5b9922"
        },
        "date": 1785191681114,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 496.5,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 496.5,
            "unit": "ns/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2410736 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 499.3,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 499.3,
            "unit": "ns/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2389692 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 496.8,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 496.8,
            "unit": "ns/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2401466 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 499.4,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 499.4,
            "unit": "ns/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2426980 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 501.2,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 501.2,
            "unit": "ns/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2414038 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1412,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1412,
            "unit": "ns/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "864606 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1337,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1337,
            "unit": "ns/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "850947 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1347,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1347,
            "unit": "ns/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "894894 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1338,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1338,
            "unit": "ns/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "863822 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1353,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1353,
            "unit": "ns/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "876792 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.75,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.75,
            "unit": "ns/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60237346 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.93,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.93,
            "unit": "ns/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60636466 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.91,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.91,
            "unit": "ns/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "58603941 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 19.03,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 19.03,
            "unit": "ns/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60419964 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 18.98,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 18.98,
            "unit": "ns/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "60538257 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 694,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 694,
            "unit": "ns/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1756176 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 693.7,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 693.7,
            "unit": "ns/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1733779 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 687.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 687.9,
            "unit": "ns/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1735542 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 692.9,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 692.9,
            "unit": "ns/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1779255 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 682.2,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 682.2,
            "unit": "ns/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1729551 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 83.06,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 83.06,
            "unit": "ns/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14475729 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 81.99,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 81.99,
            "unit": "ns/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14269443 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 82.42,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 82.42,
            "unit": "ns/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13862222 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 82.18,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 82.18,
            "unit": "ns/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14065977 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 80.87,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 80.87,
            "unit": "ns/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "14613997 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1256,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1256,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1262,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1262,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1262,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1262,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1295,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1295,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1292,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1292,
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
            "value": 68.97,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 68.97,
            "unit": "ns/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17183803 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 66.83,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 66.83,
            "unit": "ns/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17370027 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 66.88,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 66.88,
            "unit": "ns/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17918200 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 67.87,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 67.87,
            "unit": "ns/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17702191 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 66.91,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 66.91,
            "unit": "ns/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "17438637 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 2284,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 2284,
            "unit": "ns/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "707856 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1898,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1898,
            "unit": "ns/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "976533 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1855,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1855,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1836,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1836,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1833,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1833,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "value": 83.4,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 83.4,
            "unit": "ns/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14387494 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 81.42,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 81.42,
            "unit": "ns/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14553171 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 82.04,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 82.04,
            "unit": "ns/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14205252 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 83.94,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 83.94,
            "unit": "ns/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14421620 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 82.12,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 82.12,
            "unit": "ns/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "14036425 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 632.7,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 632.7,
            "unit": "ns/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1863406 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 632.5,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 632.5,
            "unit": "ns/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1872566 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 633.6,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 633.6,
            "unit": "ns/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1847499 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 648,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 648,
            "unit": "ns/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1830172 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 639.8,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 639.8,
            "unit": "ns/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1848814 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11612,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11612,
            "unit": "ns/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "109174 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11758,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11758,
            "unit": "ns/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "105176 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11572,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11572,
            "unit": "ns/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "109502 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11480,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11480,
            "unit": "ns/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "104751 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 11943,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "107949 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 11943,
            "unit": "ns/op",
            "extra": "107949 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "107949 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "107949 times\n4 procs"
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
          "id": "e588673ba085068267a472e4a89ca9be40079de1",
          "message": "ci(deps): Bump the github-actions group with 12 updates\n\nBumps the github-actions group with 12 updates:\n\n| Package | From | To |\n| --- | --- | --- |\n| [actions/checkout](https://github.com/actions/checkout) | `7.0.0` | `7.0.1` |\n| [actions/setup-python](https://github.com/actions/setup-python) | `6.3.0` | `7.0.0` |\n| [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) | `8.3.2` | `9.0.0` |\n| [github/codeql-action/upload-sarif](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [chromaui/action](https://github.com/chromaui/action) | `18.0.1` | `18.1.0` |\n| [github/codeql-action/init](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [github/codeql-action/analyze](https://github.com/github/codeql-action) | `4.37.1` | `4.37.3` |\n| [aws-actions/configure-aws-credentials](https://github.com/aws-actions/configure-aws-credentials) | `6.2.2` | `6.2.3` |\n| [docker/login-action](https://github.com/docker/login-action) | `4.4.0` | `4.5.1` |\n| [ossf/scorecard-action](https://github.com/ossf/scorecard-action) | `2.4.3` | `2.4.4` |\n| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | `3.95.9` | `3.96.0` |\n| [zizmorcore/zizmor-action](https://github.com/zizmorcore/zizmor-action) | `0.6.0` | `0.6.1` |\n\n\nUpdates `actions/checkout` from 7.0.0 to 7.0.1\n- [Release notes](https://github.com/actions/checkout/releases)\n- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/actions/checkout/compare/9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0...3d3c42e5aac5ba805825da76410c181273ba90b1)\n\nUpdates `actions/setup-python` from 6.3.0 to 7.0.0\n- [Release notes](https://github.com/actions/setup-python/releases)\n- [Commits](https://github.com/actions/setup-python/compare/v6.3.0...5fda3b95a4ea91299a34e894583c3862153e4b97)\n\nUpdates `astral-sh/setup-uv` from 8.3.2 to 9.0.0\n- [Release notes](https://github.com/astral-sh/setup-uv/releases)\n- [Commits](https://github.com/astral-sh/setup-uv/compare/11f9893b081a58869d3b5fccaea48c9e9e46f990...c771a70e6277c0a99b617c7a806ffedaca235ff9)\n\nUpdates `github/codeql-action/upload-sarif` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `chromaui/action` from 18.0.1 to 18.1.0\n- [Release notes](https://github.com/chromaui/action/releases)\n- [Changelog](https://github.com/chromaui/action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/chromaui/action/compare/94713c544284a14195de3b50ef24301579f1877e...14cfaef73576e69f95f47f60058063f46ca38719)\n\nUpdates `github/codeql-action/init` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `github/codeql-action/analyze` from 4.37.1 to 4.37.3\n- [Release notes](https://github.com/github/codeql-action/releases)\n- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/github/codeql-action/compare/7188fc363630916deb702c7fdcf4e481b751f97a...e4fba868fa4b1b91e1fdab776edc8cfbe6e9fb81)\n\nUpdates `aws-actions/configure-aws-credentials` from 6.2.2 to 6.2.3\n- [Release notes](https://github.com/aws-actions/configure-aws-credentials/releases)\n- [Changelog](https://github.com/aws-actions/configure-aws-credentials/blob/main/CHANGELOG.md)\n- [Commits](https://github.com/aws-actions/configure-aws-credentials/compare/517a711dbcd0e402f90c77e7e2f81e849156e31d...e6de054238d6b7531b4efff3b6587d9aade6a06c)\n\nUpdates `docker/login-action` from 4.4.0 to 4.5.1\n- [Release notes](https://github.com/docker/login-action/releases)\n- [Commits](https://github.com/docker/login-action/compare/af1e73f918a031802d376d3c8bbc3fe56130a9b0...abd2ef45e78c5afb21d64d4ca52ee8550d9572c7)\n\nUpdates `ossf/scorecard-action` from 2.4.3 to 2.4.4\n- [Release notes](https://github.com/ossf/scorecard-action/releases)\n- [Changelog](https://github.com/ossf/scorecard-action/blob/main/RELEASE.md)\n- [Commits](https://github.com/ossf/scorecard-action/compare/4eaacf0543bb3f2c246792bd56e8cdeffafb205a...2d1146689b8cda280b9bc96326124645441f03bc)\n\nUpdates `trufflesecurity/trufflehog` from 3.95.9 to 3.96.0\n- [Release notes](https://github.com/trufflesecurity/trufflehog/releases)\n- [Commits](https://github.com/trufflesecurity/trufflehog/compare/27b0417c16317ca9a472a9a8092acce143b49c55...6f3c981e7b77f235fd2702dd74af25fc4b72bf11)\n\nUpdates `zizmorcore/zizmor-action` from 0.6.0 to 0.6.1\n- [Release notes](https://github.com/zizmorcore/zizmor-action/releases)\n- [Commits](https://github.com/zizmorcore/zizmor-action/compare/6599ee8b7a49aef6a770f63d261d214911a7ce02...6fc4b006235f201fdab3722e17240ab420d580e5)\n\n---\nupdated-dependencies:\n- dependency-name: actions/checkout\n  dependency-version: 7.0.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: actions/setup-python\n  dependency-version: 7.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: astral-sh/setup-uv\n  dependency-version: 9.0.0\n  dependency-type: direct:production\n  update-type: version-update:semver-major\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/upload-sarif\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: chromaui/action\n  dependency-version: 18.1.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/init\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: github/codeql-action/analyze\n  dependency-version: 4.37.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: aws-actions/configure-aws-credentials\n  dependency-version: 6.2.3\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: docker/login-action\n  dependency-version: 4.5.1\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: ossf/scorecard-action\n  dependency-version: 2.4.4\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n- dependency-name: trufflesecurity/trufflehog\n  dependency-version: 3.96.0\n  dependency-type: direct:production\n  update-type: version-update:semver-minor\n  dependency-group: github-actions\n- dependency-name: zizmorcore/zizmor-action\n  dependency-version: 0.6.1\n  dependency-type: direct:production\n  update-type: version-update:semver-patch\n  dependency-group: github-actions\n...\n\nSigned-off-by: dependabot[bot] <support@github.com>\nCo-authored-by: dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>",
          "timestamp": "2026-07-28T01:31:38+03:00",
          "tree_id": "1ce958156b1aac3203b1164d4d6408db3711172c",
          "url": "https://github.com/egorribun/university_ecosystem/commit/e588673ba085068267a472e4a89ca9be40079de1"
        },
        "date": 1785191850305,
        "tool": "go",
        "benches": [
          {
            "name": "BenchmarkMessageMarshal",
            "value": 589.9,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 589.9,
            "unit": "ns/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2023942 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 589,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 589,
            "unit": "ns/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2025706 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 590.1,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 590.1,
            "unit": "ns/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2023366 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 591.8,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 591.8,
            "unit": "ns/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2032195 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal",
            "value": 594.6,
            "unit": "ns/op\t     192 B/op\t       2 allocs/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - ns/op",
            "value": 594.6,
            "unit": "ns/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - B/op",
            "value": 192,
            "unit": "B/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageMarshal - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "2017842 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1530,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1530,
            "unit": "ns/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "754741 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1525,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1525,
            "unit": "ns/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "792846 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1524,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1524,
            "unit": "ns/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "775855 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1509,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1509,
            "unit": "ns/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "770176 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal",
            "value": 1528,
            "unit": "ns/op\t     376 B/op\t      10 allocs/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - ns/op",
            "value": 1528,
            "unit": "ns/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - B/op",
            "value": 376,
            "unit": "B/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkMessageUnmarshal - allocs/op",
            "value": 10,
            "unit": "allocs/op",
            "extra": "768019 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.41,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.41,
            "unit": "ns/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86737063 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.73,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.73,
            "unit": "ns/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86561287 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.66,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.66,
            "unit": "ns/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86801869 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.78,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.78,
            "unit": "ns/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86940613 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup",
            "value": 13.84,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - ns/op",
            "value": 13.84,
            "unit": "ns/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkClientLookup - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "86674358 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 775.6,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 775.6,
            "unit": "ns/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1611675 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 732.5,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 732.5,
            "unit": "ns/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1575691 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 753.1,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 753.1,
            "unit": "ns/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1504584 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 751.3,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 751.3,
            "unit": "ns/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1611789 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room",
            "value": 762.5,
            "unit": "ns/op\t     960 B/op\t       2 allocs/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - ns/op",
            "value": 762.5,
            "unit": "ns/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - B/op",
            "value": 960,
            "unit": "B/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Room - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "1588008 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 89.12,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 89.12,
            "unit": "ns/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13148550 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 86.28,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 86.28,
            "unit": "ns/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13031815 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 86.63,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 86.63,
            "unit": "ns/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12683845 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 86.25,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 86.25,
            "unit": "ns/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "12771010 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage",
            "value": 87.42,
            "unit": "ns/op\t      80 B/op\t       2 allocs/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - ns/op",
            "value": 87.42,
            "unit": "ns/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - B/op",
            "value": 80,
            "unit": "B/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_DirectMessage - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "13529095 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1365,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1365,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1303,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1303,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1402,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1402,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1403,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1403,
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
            "name": "BenchmarkCollectRecipients_Broadcast",
            "value": 1383,
            "unit": "ns/op\t    1856 B/op\t       2 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkCollectRecipients_Broadcast - ns/op",
            "value": 1383,
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
            "value": 49.56,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 49.56,
            "unit": "ns/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25064996 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 46.8,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 46.8,
            "unit": "ns/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25933131 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 47.73,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 47.73,
            "unit": "ns/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "26122904 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 48.27,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 48.27,
            "unit": "ns/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "23641974 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend",
            "value": 46.98,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - ns/op",
            "value": 46.98,
            "unit": "ns/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkSafeSend - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "25524914 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1815,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1815,
            "unit": "ns/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
            "unit": "B/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "760688 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister",
            "value": 1553,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1553,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1572,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1572,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1570,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1570,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "name": "BenchmarkHandleRegister",
            "value": 1596,
            "unit": "ns/op\t    6863 B/op\t       8 allocs/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - ns/op",
            "value": 1596,
            "unit": "ns/op",
            "extra": "1000000 times\n4 procs"
          },
          {
            "name": "BenchmarkHandleRegister - B/op",
            "value": 6863,
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
            "value": 63.55,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 63.55,
            "unit": "ns/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18452878 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 67.13,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 67.13,
            "unit": "ns/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18872322 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 64.01,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 64.01,
            "unit": "ns/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18766596 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 63.62,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 63.62,
            "unit": "ns/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18802897 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated",
            "value": 72.46,
            "unit": "ns/op\t       0 B/op\t       0 allocs/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - ns/op",
            "value": 72.46,
            "unit": "ns/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - B/op",
            "value": 0,
            "unit": "B/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkNATSPublishSimulated - allocs/op",
            "value": 0,
            "unit": "allocs/op",
            "extra": "18385593 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 691.7,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 691.7,
            "unit": "ns/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1727047 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 696,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 696,
            "unit": "ns/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1722208 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 695.2,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 695.2,
            "unit": "ns/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1729167 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 694.4,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 694.4,
            "unit": "ns/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1728932 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify",
            "value": 693.9,
            "unit": "ns/op\t     640 B/op\t       8 allocs/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - ns/op",
            "value": 693.9,
            "unit": "ns/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - B/op",
            "value": 640,
            "unit": "B/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkJWTVerify - allocs/op",
            "value": 8,
            "unit": "allocs/op",
            "extra": "1729224 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12992,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12992,
            "unit": "ns/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "94572 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12921,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12921,
            "unit": "ns/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93693 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12838,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12838,
            "unit": "ns/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "94436 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12907,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12907,
            "unit": "ns/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "92946 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients",
            "value": 12983,
            "unit": "ns/op\t   16448 B/op\t       2 allocs/op",
            "extra": "93988 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - ns/op",
            "value": 12983,
            "unit": "ns/op",
            "extra": "93988 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - B/op",
            "value": 16448,
            "unit": "B/op",
            "extra": "93988 times\n4 procs"
          },
          {
            "name": "BenchmarkBroadcastTo1000Clients - allocs/op",
            "value": 2,
            "unit": "allocs/op",
            "extra": "93988 times\n4 procs"
          }
        ]
      }
    ]
  }
}