package hub

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/require"
)

func TestTargetedInvalidationRetiresPendingAllowAndWaiter(t *testing.T) {
	for _, mode := range []string{"room", "user", "refresh"} {
		t.Run(mode, func(t *testing.T) {
			mr, rc := newMiniredisClient(t)
			started, release := make(chan struct{}), make(chan struct{})
			var releaseOnce sync.Once
			var requests atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if requests.Add(1) == 1 {
					close(started)
					select {
					case <-release:
					case <-r.Context().Done():
						return
					}
					w.WriteHeader(http.StatusOK)
					return
				}
				w.WriteHeader(http.StatusForbidden)
			}))
			t.Cleanup(server.Close)
			t.Cleanup(func() { releaseOnce.Do(func() { close(release) }) })
			client := mustNewTestAuthClient(t, server.URL, "", rc)
			leader := make(chan bool, 1)
			go func() { leader <- client.CanJoinRoom(context.Background(), rdUser, rdRoom) }()
			waitRoomMembershipSignal(t, started, "old backend allow did not start")
			observed := &observedDoneContext{Context: context.Background(), observed: make(chan struct{})}
			waiter := make(chan bool, 1)
			go func() {
				waiter <- client.requestRoomAuthorization(observed, rdUser, rdRoom, rdUser+":"+rdRoom, 0)
			}()
			waitRoomMembershipSignal(t, observed.observed, "waiter did not join old flight")

			switch mode {
			case "room":
				client.Invalidate(rdUser, rdRoom)
			case "user":
				client.Invalidate(rdUser, "")
			case "refresh":
				allowed, err := client.RefreshRoomAuthorization(context.Background(), rdUser, rdRoom)
				require.NoError(t, err)
				require.False(t, allowed)
			}
			releaseOnce.Do(func() { close(release) })
			require.False(t, <-leader, "late old allow must not authorize the leader")
			require.False(t, <-waiter, "pending old waiter must not receive retired allow")
			assertRoomAuthorizationNotCached(t, mr, client, rdUser, rdRoom)
			require.False(t, client.CanJoinRoom(context.Background(), rdUser, rdRoom),
				"next join must obtain the current backend denial")
			entry, ok := client.cache.Get(rdUser + ":" + rdRoom)
			require.True(t, ok)
			require.False(t, entry.allowed)
		})
	}
}

func TestTargetedInvalidationPreservesReplacementFlight(t *testing.T) {
	oldStarted, newStarted := make(chan struct{}), make(chan struct{})
	oldRelease, newRelease := make(chan struct{}), make(chan struct{})
	var oldOnce, newOnce sync.Once
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch calls.Add(1) {
		case 1:
			close(oldStarted)
			select {
			case <-oldRelease:
			case <-r.Context().Done():
				return
			}
			w.WriteHeader(http.StatusOK)
		case 2:
			close(newStarted)
			select {
			case <-newRelease:
			case <-r.Context().Done():
				return
			}
			w.WriteHeader(http.StatusForbidden)
		default:
			t.Error("unexpected additional backend call")
			w.WriteHeader(http.StatusForbidden)
		}
	}))
	t.Cleanup(server.Close)
	t.Cleanup(func() {
		oldOnce.Do(func() { close(oldRelease) })
		newOnce.Do(func() { close(newRelease) })
	})
	client := mustNewTestAuthClient(t, server.URL, "", nil)
	oldDone, newDone := make(chan bool, 1), make(chan bool, 1)
	go func() { oldDone <- client.CanJoinRoom(context.Background(), rdUser, rdRoom) }()
	waitRoomMembershipSignal(t, oldStarted, "old flight did not start")
	client.Invalidate(rdUser, rdRoom)
	go func() { newDone <- client.CanJoinRoom(context.Background(), rdUser, rdRoom) }()
	waitRoomMembershipSignal(t, newStarted, "new caller joined retired flight")
	client.callMu.Lock()
	current := client.calls[rdUser+":"+rdRoom]
	client.callMu.Unlock()
	oldOnce.Do(func() { close(oldRelease) })
	require.False(t, <-oldDone)
	client.callMu.Lock()
	retained := client.calls[rdUser+":"+rdRoom]
	client.callMu.Unlock()
	require.Same(t, current, retained, "old cleanup must preserve replacement")
	newOnce.Do(func() { close(newRelease) })
	require.False(t, <-newDone)
	require.EqualValues(t, 2, calls.Load())
}

func TestTargetedInvalidationLeavesUnrelatedKeysUntouched(t *testing.T) {
	const otherUser = "44444444-4444-4444-4444-444444444444"
	client := mustNewTestAuthClient(t, "http://unused.invalid", "", nil)
	target := &call{}
	otherRoom := &call{}
	otherOwner := &call{}
	client.calls[rdUser+":"+rdRoom] = target
	client.calls[rdUser+":"+rdRoom2] = otherRoom
	client.calls[otherUser+":"+rdRoom] = otherOwner
	for key := range client.calls {
		client.cache.Add(key, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Minute)})
	}

	client.Invalidate(rdUser, rdRoom)
	require.True(t, target.retired)
	require.False(t, otherRoom.retired)
	require.False(t, otherOwner.retired)
	require.Equal(t, 2, client.cache.Len())

	client.Invalidate(rdUser, "")
	require.True(t, otherRoom.retired)
	require.False(t, otherOwner.retired)
	require.Equal(t, 1, client.cache.Len())
	require.True(t, client.CanJoinRoom(context.Background(), otherUser, rdRoom))
}

func TestTargetedInvalidationRetiresLocalStateOnRedisFailure(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	client := mustNewTestAuthClient(t, "http://unused.invalid", "", rc)
	pending := &call{}
	client.calls[rdUser+":"+rdRoom] = pending
	client.cache.Add(rdUser+":"+rdRoom, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Minute)})
	mr.SetError("ERR synthetic invalidation failure")

	allowed, err := client.RefreshRoomAuthorization(context.Background(), rdUser, rdRoom)
	require.Error(t, err)
	require.False(t, allowed)
	require.True(t, pending.retired)
	require.Zero(t, client.cache.Len())
	require.Error(t, client.invalidateRoomAuthorizationCache(context.Background(), rdUser, ""))
}

type targetedInvalidationDeleteHook struct {
	after func()
	fail  bool
}

func (h targetedInvalidationDeleteHook) DialHook(next redis.DialHook) redis.DialHook {
	return next
}

func (h targetedInvalidationDeleteHook) ProcessPipelineHook(next redis.ProcessPipelineHook) redis.ProcessPipelineHook {
	return next
}

func (h targetedInvalidationDeleteHook) ProcessHook(next redis.ProcessHook) redis.ProcessHook {
	return func(ctx context.Context, cmd redis.Cmder) error {
		if cmd.Name() == "del" && h.fail {
			return errors.New("synthetic delete failure")
		}
		err := next(ctx, cmd)
		if cmd.Name() == "del" && h.after != nil {
			h.after()
		}
		return err
	}
}

func TestTargetedInvalidationClearsStateCreatedDuringRedisIO(t *testing.T) {
	_, rc := newMiniredisClient(t)
	deleted, release := make(chan struct{}), make(chan struct{})
	var releaseOnce sync.Once
	rc.AddHook(targetedInvalidationDeleteHook{after: func() {
		close(deleted)
		<-release
	}})
	client := mustNewTestAuthClient(t, "http://unused.invalid", "", rc)
	done := make(chan error, 1)
	go func() {
		done <- client.invalidateRoomAuthorizationCache(context.Background(), rdUser, rdRoom)
	}()
	t.Cleanup(func() { releaseOnce.Do(func() { close(release) }) })
	waitRoomMembershipSignal(t, deleted, "Redis deletion did not reach barrier")
	// Model an L2 reader/new HTTP flight admitted while network I/O is pending.
	// genMu must remain available, and the final sweep must retire this state.
	late := &call{}
	published := make(chan struct{})
	go func() {
		client.genMu.Lock()
		client.callMu.Lock()
		client.calls[rdUser+":"+rdRoom] = late
		client.callMu.Unlock()
		client.cache.Add(rdUser+":"+rdRoom, cacheEntry{allowed: true})
		client.genMu.Unlock()
		close(published)
	}()
	waitRoomMembershipSignal(t, published, "Redis I/O held the generation lock")
	releaseOnce.Do(func() { close(release) })
	require.NoError(t, <-done)
	require.True(t, late.retired)
	require.Zero(t, client.cache.Len())
}

func TestTargetedWildcardInvalidationPropagatesDeleteFailure(t *testing.T) {
	mr, rc := newMiniredisClient(t)
	require.NoError(t, mr.Set("auth:perms:"+rdUser+":"+rdRoom, "1"))
	rc.AddHook(targetedInvalidationDeleteHook{fail: true})
	client := mustNewTestAuthClient(t, "http://unused.invalid", "", rc)
	require.ErrorContains(t,
		client.invalidateRoomAuthorizationCache(context.Background(), rdUser, ""),
		"synthetic delete failure")
}

func TestTargetedInvalidationBlocksPublicationAfterRedisDelete(t *testing.T) {
	for _, mode := range []string{"room", "user", "urn-user"} {
		t.Run(mode, func(t *testing.T) {
			mr, rc := newMiniredisClient(t)
			userID, roomID := rdUser, rdRoom
			if mode == "urn-user" {
				userID, roomID = "urn:uuid:"+rdUser, "urn:uuid:"+rdRoom
			}
			key := userID + ":" + roomID
			require.NoError(t, mr.Set("auth:perms:"+key, "1"))
			deleted, release := make(chan struct{}), make(chan struct{})
			var releaseOnce sync.Once
			var requests atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				requests.Add(1)
				w.WriteHeader(http.StatusOK)
			}))
			t.Cleanup(server.Close)
			t.Cleanup(func() { releaseOnce.Do(func() { close(release) }) })
			rc.AddHook(targetedInvalidationDeleteHook{after: func() {
				close(deleted)
				<-release
			}})
			client := mustNewTestAuthClient(t, server.URL, "", rc)
			done := make(chan error, 1)
			room := roomID
			if mode != "room" {
				room = ""
			}
			go func() {
				done <- client.invalidateRoomAuthorizationCache(context.Background(), userID, room)
			}()
			waitRoomMembershipSignal(t, deleted, "DEL did not finish before lookup")
			// Real cache-miss/HTTP/publication path: without the barrier this
			// obtains 200 and SETs L2 after DEL, beyond the final local sweep.
			require.False(t, client.CanJoinRoom(context.Background(), userID, roomID))
			require.False(t, client.requestRoomAuthorization(context.Background(), userID, roomID, key, 0))
			require.Zero(t, requests.Load())
			assertRoomAuthorizationNotCached(t, mr, client, userID, roomID)
			releaseOnce.Do(func() { close(release) })
			require.NoError(t, <-done)
			require.Empty(t, client.invalidations)
			assertRoomAuthorizationNotCached(t, mr, client, userID, roomID)
			require.True(t, client.CanJoinRoom(context.Background(), userID, roomID),
				"the barrier must not permanently revoke backend-authorized access")
			require.EqualValues(t, 1, requests.Load())
		})
	}
}

func TestTargetedInvalidationOverlappingBarriers(t *testing.T) {
	for _, rooms := range [][2]string{{rdRoom, rdRoom}, {"", rdRoom}, {rdRoom, ""}} {
		t.Run(rooms[0]+"/"+rooms[1], func(t *testing.T) {
			mr, rc := newMiniredisClient(t)
			key := rdUser + ":" + rdRoom
			first, second := make(chan struct{}), make(chan struct{})
			releaseFirst, releaseSecond := make(chan struct{}), make(chan struct{})
			var onceFirst, onceSecond sync.Once
			var deletes atomic.Int32
			rc.AddHook(targetedInvalidationDeleteHook{after: func() {
				if deletes.Add(1) == 1 {
					close(first)
					<-releaseFirst
				} else {
					close(second)
					<-releaseSecond
				}
			}})
			t.Cleanup(func() {
				onceFirst.Do(func() { close(releaseFirst) })
				onceSecond.Do(func() { close(releaseSecond) })
			})
			client := mustNewTestAuthClient(t, "http://unused.invalid", "", rc)
			doneFirst, doneSecond := make(chan error, 1), make(chan error, 1)
			require.NoError(t, mr.Set("auth:perms:"+key, "1"))
			go func() { doneFirst <- client.invalidateRoomAuthorizationCache(context.Background(), rdUser, rooms[0]) }()
			waitRoomMembershipSignal(t, first, "first invalidation did not reach DEL")
			// Model a different replica's entry so wildcard SCAN reaches DEL too.
			require.NoError(t, mr.Set("auth:perms:"+key, "1"))
			go func() { doneSecond <- client.invalidateRoomAuthorizationCache(context.Background(), rdUser, rooms[1]) }()
			waitRoomMembershipSignal(t, second, "second invalidation did not reach DEL")
			onceFirst.Do(func() { close(releaseFirst) })
			require.NoError(t, <-doneFirst)
			client.genMu.RLock()
			active := client.invalidationActive(rdUser, key)
			client.genMu.RUnlock()
			require.True(t, active, "first completion must not release overlapping barrier")
			require.False(t, client.CanJoinRoom(context.Background(), rdUser, rdRoom))
			const otherUser = "44444444-4444-4444-4444-444444444444"
			client.cache.Add(otherUser+":"+rdRoom, cacheEntry{allowed: true, expiresAt: time.Now().Add(time.Minute)})
			require.True(t, client.CanJoinRoom(context.Background(), otherUser, rdRoom))
			onceSecond.Do(func() { close(releaseSecond) })
			require.NoError(t, <-doneSecond)
			require.Empty(t, client.invalidations)
		})
	}
}

func TestInvalidationBarrierAcceptsUUIDEncodings(t *testing.T) {
	for _, encode := range []func(string) string{
		func(id string) string { return id },
		func(id string) string { return strings.ReplaceAll(id, "-", "") },
		func(id string) string { return "{" + id + "}" },
		func(id string) string { return "urn:uuid:" + id },
	} {
		userID, roomID := encode(rdUser), encode(rdRoom)
		t.Run(userID, func(t *testing.T) {
			require.True(t, isValidUUID(userID))
			require.True(t, isValidUUID(roomID))
			client := mustNewTestAuthClient(t, "http://unused.invalid", "", nil)
			client.invalidations = map[string]int{userID + ":": 1}
			require.True(t, client.invalidationActive(userID, userID+":"+roomID))
			require.False(t, client.invalidationActive(rdRoom2, rdRoom2+":"+roomID))
			client.invalidations = map[string]int{userID + ":" + roomID: 1}
			require.True(t, client.invalidationActive(userID, userID+":"+roomID))
			require.False(t, client.invalidationActive(userID, userID+":"+rdRoom2))
		})
	}
	for _, invalid := range []string{"", "urn:uuid:invalid", rdUser + ":extra", "*", rdUser + "?admin=true"} {
		client := mustNewTestAuthClient(t, "http://unused.invalid", "", nil)
		require.False(t, isValidUUID(invalid))
		require.False(t, client.CanJoinRoom(context.Background(), invalid, rdRoom))
		require.False(t, client.CanJoinRoom(context.Background(), rdUser, invalid))
		client.Invalidate(invalid, rdRoom)
		require.Empty(t, client.invalidations)
	}
}
