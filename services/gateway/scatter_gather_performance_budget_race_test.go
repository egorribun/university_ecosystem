//go:build race

package gateway

import "time"

// The race detector instruments every map/slice access and makes this
// allocation-heavy empirical test materially slower. Keep a finite budget so
// regressions still fail without treating instrumentation overhead as a
// production latency regression.
const scatterGatherMergerBudget = 250 * time.Millisecond
