//go:build contract

package hub

import (
	"context"
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"strconv"
	"testing"

	"github.com/nats-io/nats.go"
	"github.com/stretchr/testify/require"
)

// Python's WsHubClient and NatsTaskBroker generated these bytes in the
// consumer job. The JetStream transport is captured; no NATS server is used.
type auditWireEvent struct {
	Subject string            `json:"subject"`
	Wire    string            `json:"wire"`
	Headers map[string]string `json:"headers"`
}

type auditWireFixture struct {
	TestHMACKey string           `json:"test_hmac_key"`
	Events      []auditWireEvent `json:"events"`
}

type auditRoomAuth struct {
	invalidations [][2]string
	refreshes     [][2]string
}

func (a *auditRoomAuth) CanJoinRoom(context.Context, string, string) bool { return false }
func (a *auditRoomAuth) Invalidate(user, room string) {
	a.invalidations = append(a.invalidations, [2]string{user, room})
}
func (a *auditRoomAuth) RefreshRoomAuthorization(_ context.Context, user, room string) (bool, error) {
	a.refreshes = append(a.refreshes, [2]string{user, room})
	return false, nil
}

// Bind the captured subjects to the production subscriptions as well as the
// handlers. This source check does not simulate a live JetStream subscription.
// It returns the subject bound to each cache-invalidation handler variable:
// invHandler carries pure invalidations and revocationHandler carries room
// revocations (evict_room).
func auditInvalidationSubscriptions(t *testing.T) map[string]string {
	t.Helper()
	file, err := parser.ParseFile(token.NewFileSet(), "hub.go", nil, 0)
	require.NoError(t, err)
	subjects := map[string]string{}
	handlerBound := map[string]bool{}
	for _, declaration := range file.Decls {
		fn, ok := declaration.(*ast.FuncDecl)
		if !ok || fn.Name.Name != "SubscribeToNATS" || fn.Body == nil {
			continue
		}
		ast.Inspect(fn.Body, func(node ast.Node) bool {
			if assignment, ok := node.(*ast.AssignStmt); ok && len(assignment.Lhs) == 1 && len(assignment.Rhs) == 1 {
				name, nameOK := assignment.Lhs[0].(*ast.Ident)
				call, callOK := assignment.Rhs[0].(*ast.CallExpr)
				if nameOK && callOK && (name.Name == "invHandler" || name.Name == "revocationHandler") {
					selector, selectorOK := call.Fun.(*ast.SelectorExpr)
					if selectorOK {
						receiver, receiverOK := selector.X.(*ast.Ident)
						handlerBound[name.Name] = receiverOK && receiver.Name == "h" && selector.Sel.Name == "handleCacheInvalidation"
					}
				}
			}
			call, ok := node.(*ast.CallExpr)
			if !ok || len(call.Args) < 2 {
				return true
			}
			selector, ok := call.Fun.(*ast.SelectorExpr)
			if !ok || selector.Sel.Name != "Subscribe" {
				return true
			}
			js, ok := selector.X.(*ast.SelectorExpr)
			if !ok || js.Sel.Name != "js" {
				return true
			}
			receiver, ok := js.X.(*ast.Ident)
			handler, handlerOK := call.Args[1].(*ast.Ident)
			subject, subjectOK := call.Args[0].(*ast.BasicLit)
			if ok && receiver.Name == "h" && handlerOK && (handler.Name == "invHandler" || handler.Name == "revocationHandler") && subjectOK && subject.Kind == token.STRING {
				value, err := strconv.Unquote(subject.Value)
				require.NoError(t, err)
				subjects[handler.Name] = value
			}
			return true
		})
	}
	require.True(t, handlerBound["invHandler"], "pure invalidation subscription must bind the production handler")
	require.True(t, handlerBound["revocationHandler"], "revocation subscription must bind the production handler")
	require.Equal(t, map[string]string{
		"invHandler":        "cache.invalidate",
		"revocationHandler": "cache.revoke",
	}, subjects, "each invalidation class must have exactly one production subscription")
	return subjects
}

func TestPythonCacheInvalidationWire(t *testing.T) {
	path := os.Getenv("WS_HUB_WIRE_FIXTURES")
	require.NotEmpty(t, path, "the Python producer artifact is required")
	data, err := os.ReadFile(path)
	require.NoError(t, err)
	var fixture auditWireFixture
	require.NoError(t, json.Unmarshal(data, &fixture))
	require.NotEmpty(t, fixture.TestHMACKey, "per-run test key is required")
	require.Len(t, fixture.Events, 3)
	subjects := auditInvalidationSubscriptions(t)

	const user = "11111111-1111-1111-1111-111111111111"
	const room = "22222222-2222-2222-2222-222222222222"
	cases := []struct {
		name, room, messageID, handler string
		evict                          bool
	}{
		{"room", room, "contract-room", "invHandler", false},
		{"user-wide", "", "contract-user-wide", "invHandler", false},
		{"eviction", room, "contract-eviction", "revocationHandler", true},
	}

	oldAck, oldTerm := jetStreamAckFunc, jetStreamTermFunc
	defer func() { jetStreamAckFunc, jetStreamTermFunc = oldAck, oldTerm }()
	for i, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			event := fixture.Events[i]
			require.Equal(t, subjects[tc.handler], event.Subject,
				"the Python publisher must use the subject its production consumer reads")
			require.Equal(t, tc.messageID, event.Headers["Nats-Msg-Id"])
			auth := &auditRoomAuth{}
			h := newNatsTestHub(auth, fixture.TestHMACKey, 10)
			ack, term := 0, 0
			jetStreamAckFunc = func(*nats.Msg) error { ack++; return nil }
			jetStreamTermFunc = func(*nats.Msg) error { term++; return nil }

			h.handleCacheInvalidation(context.Background())(&nats.Msg{
				Subject: event.Subject, Data: []byte(event.Wire),
			})
			require.Equal(t, 1, ack)
			require.Zero(t, term)
			if tc.evict {
				require.Equal(t, [][2]string{{user, tc.room}}, auth.refreshes)
				require.Empty(t, auth.invalidations)
			} else {
				require.Equal(t, [][2]string{{user, tc.room}}, auth.invalidations)
				require.Empty(t, auth.refreshes)
			}

			// Preserve the original signature while changing a valid field.
			var tampered map[string]any
			require.NoError(t, json.Unmarshal([]byte(event.Wire), &tampered))
			content, ok := tampered["data"].(map[string]any)
			require.True(t, ok)
			content["user_id"] = "33333333-3333-3333-3333-333333333333"
			body, err := json.Marshal(tampered)
			require.NoError(t, err)
			auth.invalidations, auth.refreshes = nil, nil
			h.handleCacheInvalidation(context.Background())(&nats.Msg{
				Subject: event.Subject, Data: body,
			})
			require.Equal(t, 1, ack, "tampered body must not be acknowledged")
			require.Equal(t, 1, term, "tampered body must be rejected")
			require.Empty(t, auth.invalidations)
			require.Empty(t, auth.refreshes)
		})
	}
}
