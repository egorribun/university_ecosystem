window.BENCHMARK_DATA = {
  "lastUpdate": 1784817312809,
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
      }
    ]
  }
}