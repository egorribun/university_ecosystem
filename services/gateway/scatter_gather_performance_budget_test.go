//go:build !race

package gateway

import "time"

const scatterGatherMergerBudget = 50 * time.Millisecond
