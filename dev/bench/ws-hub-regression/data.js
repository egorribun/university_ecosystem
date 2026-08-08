window.BENCHMARK_DATA = {
  "lastUpdate": 1786214924118,
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
      }
    ]
  }
}