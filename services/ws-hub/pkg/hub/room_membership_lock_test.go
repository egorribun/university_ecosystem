package hub

import (
	"strconv"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestRoomMembershipLockDoesNotSerializeDistinctCollidingKeys(t *testing.T) {
	const userID = "user-1"
	const firstRoomID = "collision-68"
	const secondRoomID = "collision-86"

	require.Equal(t, legacyRoomMembershipStripe(userID, firstRoomID), legacyRoomMembershipStripe(userID, secondRoomID),
		"regression keys must collide under the previous 256-stripe scheme")

	h := setupTestHub()
	first := h.roomMembershipLock(userID, firstRoomID)
	second := h.roomMembershipLock(userID, secondRoomID)
	first.Lock()
	if !second.TryLock() {
		first.Unlock()
		t.Fatal("a different user/room key must not wait for a colliding membership lock")
	}
	second.Unlock()
	first.Unlock()
}

func TestRoomMembershipLockSerializesSameKeyAndReclaimsIdleEntries(t *testing.T) {
	const userID = "user-with-active-membership"
	const roomID = "room-with-active-membership"

	h := setupTestHub()
	first := h.roomMembershipLock(userID, roomID)
	first.Lock()
	firstHeld := true
	unlockFirst := func() {
		if firstHeld {
			first.Unlock()
			firstHeld = false
		}
	}
	waiterRegistered := make(chan struct{})
	waiterAcquired := make(chan struct{})
	waiterDone := make(chan struct{})
	go func() {
		waiter := h.roomMembershipLock(userID, roomID)
		close(waiterRegistered)
		waiter.Lock()
		close(waiterAcquired)
		waiter.Unlock()
		close(waiterDone)
	}()
	t.Cleanup(func() {
		unlockFirst()
		select {
		case <-waiterDone:
		case <-time.After(time.Second):
			t.Error("same-key waiter did not exit during test cleanup")
		}
	})
	require.False(t, h.roomMembershipLock(userID, roomID).TryLock(), "same-key operations must serialize")
	select {
	case <-waiterRegistered:
	case <-time.After(time.Second):
		t.Fatal("same-key waiter did not register")
	}

	h.roomMembershipLocks.mu.Lock()
	entry := h.roomMembershipLocks.entries[roomMembershipKey{userID: userID, roomID: roomID}]
	var references int
	if entry != nil {
		references = entry.references
	}
	h.roomMembershipLocks.mu.Unlock()
	require.NotNil(t, entry, "the held lock and waiter must share a live entry")
	require.Equal(t, 2, references, "entry lifetime must include both holder and waiter")
	select {
	case <-waiterAcquired:
		unlockFirst()
		t.Fatal("same-key waiter acquired before the holder released the lock")
	default:
	}

	unlockFirst()
	select {
	case <-waiterAcquired:
	case <-time.After(time.Second):
		t.Fatal("same-key waiter did not acquire after the holder released the lock")
	}
	select {
	case <-waiterDone:
	case <-time.After(time.Second):
		t.Fatal("same-key waiter did not release its lock reference")
	}

	h.roomMembershipLocks.mu.Lock()
	remainingEntries := len(h.roomMembershipLocks.entries)
	h.roomMembershipLocks.mu.Unlock()
	require.Zero(t, remainingEntries, "idle room-membership entries must be reclaimed")

	completedOperations := 0
	for index := 0; index < 256; index++ {
		lock := h.roomMembershipLock(userID, "transient-room-"+strconv.Itoa(index))
		lock.Lock()
		completedOperations++
		lock.Unlock()
	}
	require.Equal(t, 256, completedOperations)
	h.roomMembershipLocks.mu.Lock()
	remainingEntries = len(h.roomMembershipLocks.entries)
	h.roomMembershipLocks.mu.Unlock()
	require.Zero(t, remainingEntries, "distinct completed keys must not accumulate entries")
}

func legacyRoomMembershipStripe(userID, roomID string) uint64 {
	const (
		fnvOffset = uint64(14695981039346656037)
		fnvPrime  = uint64(1099511628211)
	)
	hash := fnvOffset
	for i := 0; i < len(userID); i++ {
		hash ^= uint64(userID[i])
		hash *= fnvPrime
	}
	hash *= fnvPrime
	for i := 0; i < len(roomID); i++ {
		hash ^= uint64(roomID[i])
		hash *= fnvPrime
	}
	return hash % 256
}
