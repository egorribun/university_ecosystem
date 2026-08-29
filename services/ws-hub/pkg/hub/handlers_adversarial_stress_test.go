package hub

import (
	"context"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestAdversarial_ValidateTicketFormat_ExhaustiveFuzz(t *testing.T) {
	// Adversarial inputs for validateTicketFormat
	validHex64 := strings.Repeat("a1", 32)
	require.NoError(t, validateTicketFormat(validHex64))

	invalidCases := []struct {
		name   string
		ticket string
		errMsg string
	}{
		{"empty", "", "invalid ticket length: 0"},
		{"1 byte", "a", "invalid ticket length: 1"},
		{"63 bytes", strings.Repeat("a", 63), "invalid ticket length: 63"},
		{"65 bytes", strings.Repeat("a", 65), "invalid ticket length: 65"},
		{"null bytes in 64 len", strings.Repeat("a", 32) + "\x00" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"newline in 64 len", strings.Repeat("a", 32) + "\n" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"space in 64 len", strings.Repeat("a", 32) + " " + strings.Repeat("a", 31), "invalid ticket charset"},
		{"uppercase hex char", strings.Repeat("a", 32) + "A" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"all uppercase", strings.Repeat("F", 64), "invalid ticket charset"},
		{"g character", strings.Repeat("a", 32) + "g" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"z character", strings.Repeat("a", 32) + "z" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"hyphen character", strings.Repeat("a", 32) + "-" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"underscore character", strings.Repeat("a", 32) + "_" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"slash character", strings.Repeat("a", 32) + "/" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"colon character", strings.Repeat("a", 32) + ":" + strings.Repeat("a", 31), "invalid ticket charset"},
		{"unicode emoji", strings.Repeat("a", 60) + "🚀", "invalid ticket charset"},
		{"sql injection attempt", "' OR '1'='1' -- " + strings.Repeat("a", 48), "invalid ticket charset"},
	}

	for _, tc := range invalidCases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateTicketFormat(tc.ticket)
			require.Error(t, err)
			assert.Contains(t, err.Error(), tc.errMsg)
		})
	}
}

func TestAdversarial_ParseTicketPayload_ExhaustiveFuzz(t *testing.T) {
	// Valid payload
	u, j, err := parseTicketPayload("usr-12345:jti-abcde")
	require.NoError(t, err)
	assert.Equal(t, "usr-12345", u)
	assert.Equal(t, "jti-abcde", j)

	invalidPayloads := []string{
		"",
		":",
		"::",
		":::",
		":jti_only",
		"user_only:",
		"user:jti:extra",
		"user:jti:extra:more",
		"no_colons_at_all",
		" ",
		":\n",
	}

	for _, p := range invalidPayloads {
		t.Run("payload_"+p, func(t *testing.T) {
			_, _, err := parseTicketPayload(p)
			require.Error(t, err)
			assert.Contains(t, err.Error(), "malformed ticket payload")
		})
	}
}

func TestAdversarial_ValidateUpgradeTicket_ConcurrentRace(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		require.NoError(t, rdb.Close())
	})

	h := setupTestHub()
	h.redisClient = rdb
	h.revocationRedisClient = rdb

	ticket := strings.Repeat("b2", 32)
	require.NoError(t, mr.Set(wsTicketKeyPrefix+ticket, "racing-user:"+validSessionJTI))

	const concurrency = 50
	var successCount atomic.Int32
	var notFoundCount atomic.Int32
	var otherErrors atomic.Int32

	var wg sync.WaitGroup
	wg.Add(concurrency)

	startGate := make(chan struct{})

	for i := 0; i < concurrency; i++ {
		go func() {
			defer wg.Done()
			<-startGate
			userID, _, err := h.validateUpgradeTicket(context.Background(), ticket)
			if err == nil && userID == "racing-user" {
				successCount.Add(1)
			} else if err != nil && strings.Contains(err.Error(), "not found or already used") {
				notFoundCount.Add(1)
			} else {
				otherErrors.Add(1)
			}
		}()
	}

	close(startGate)
	wg.Wait()

	assert.Equal(t, int32(1), successCount.Load(), "Exactly ONE caller must win the single-use ticket race")
	assert.Equal(t, int32(concurrency-1), notFoundCount.Load(), "All other callers must get 'not found or already used'")
	assert.Equal(t, int32(0), otherErrors.Load(), "Zero unexpected errors")
}

func TestAdversarial_ValidateUpgradeTicket_RevocationScenarios(t *testing.T) {
	mr := miniredis.RunT(t)
	rdb := goredis.NewClient(&goredis.Options{Addr: mr.Addr()})
	t.Cleanup(func() {
		require.NoError(t, rdb.Close())
	})

	revMr := miniredis.RunT(t)
	revRdb := goredis.NewClient(&goredis.Options{Addr: revMr.Addr()})
	t.Cleanup(func() {
		require.NoError(t, revRdb.Close())
	})

	h := setupTestHub()
	h.redisClient = rdb
	h.revocationRedisClient = revRdb

	// 1. Unrevoked ticket
	ticket1 := strings.Repeat("c3", 32)
	require.NoError(t, mr.Set(wsTicketKeyPrefix+ticket1, "alice:"+validSessionJTI))
	userID, _, err := h.validateUpgradeTicket(context.Background(), ticket1)
	require.NoError(t, err)
	assert.Equal(t, "alice", userID)

	// 2. Revoked ticket (key exists in revocation Redis)
	ticket2 := strings.Repeat("d4", 32)
	require.NoError(t, mr.Set(wsTicketKeyPrefix+ticket2, "bob:"+validSessionJTI))
	require.NoError(t, revMr.Set(revokedJTIKeyPrefix+validSessionJTI, "1"))
	_, _, err = h.validateUpgradeTicket(context.Background(), ticket2)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "ticket session is revoked")

	// 3. Revocation Redis network failure / close
	ticket3 := strings.Repeat("e5", 32)
	require.NoError(t, mr.Set(wsTicketKeyPrefix+ticket3, "carol:"+validSessionJTI))
	revMr.Close() // simulate crash / network partition
	_, _, err = h.validateUpgradeTicket(context.Background(), ticket3)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "session revocation check failed")
}
