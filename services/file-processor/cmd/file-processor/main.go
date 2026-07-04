package main

import (
	"context"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/graph-gophers/graphql-go"
	"github.com/graph-gophers/graphql-go/relay"
	"github.com/grpc-ecosystem/go-grpc-middleware/v2/interceptors/auth"
	grpc_prometheus "github.com/grpc-ecosystem/go-grpc-prometheus"
	"github.com/nats-io/nats.go"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	enumspb "go.temporal.io/api/enums/v1"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/worker"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/health"
	"google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/reflection"
	"google.golang.org/grpc/status"

	"github.com/getsentry/sentry-go"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.27.0"

	pb "github.com/university-ecosystem/core/gen/go/file_processor/v1"
	"github.com/university-ecosystem/file-processor/internal/config"
	gql "github.com/university-ecosystem/file-processor/internal/graphql"
	"github.com/university-ecosystem/file-processor/internal/middleware"
	"github.com/university-ecosystem/file-processor/internal/service"
	"github.com/university-ecosystem/file-processor/internal/workflow"
)

type contextKey string

const (
	userIDKey contextKey = "user_id"
)

var (
	dialTemporalFunc = client.Dial
	newWorkerFunc    = worker.New
)



func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	runMain(ctx)
}

func runMain(ctx context.Context) {
	logger := initLogger()

	cfg, err := config.Load()
	if err != nil {
		logger.ErrorContext(ctx, "Failed to load configuration", "err", err)
		os.Exit(1)
	}

	// TD-W18-01 (audit 2026-03-23 Wave 18): parse RSA public key for RS256 support.
	var rsaPublicKey *rsa.PublicKey
	if cfg.RSAPublicKeyPEM != "" {
		rsaPublicKey, err = parseRSAPublicKey(cfg.RSAPublicKeyPEM)
		if err != nil {
			logger.ErrorContext(ctx, "Failed to parse RSA_PUBLIC_KEY_PEM", "err", err)
			os.Exit(1)
		}
		logger.InfoContext(ctx, "RS256 token verification enabled")
	}
	initSentry(ctx, cfg, logger)

	tp, err := initTracer(ctx, cfg, logger)
	if err != nil {
		logger.ErrorContext(ctx, "OpenTelemetry initialization failed", "err", err)
	} else {
		defer func() {
			if shutErr := tp.Shutdown(ctx); shutErr != nil {
				logger.WarnContext(ctx, "Failed to shutdown tracer provider", "err", shutErr)
			}
		}()
	}

	c, err := connectTemporal(ctx, cfg, logger)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to connect to Temporal", "err", err)
		os.Exit(1)
	}
	defer c.Close()

	w, _ := setupTemporalWorker(ctx, c, cfg, logger)
	if err := w.Start(); err != nil {
		logger.ErrorContext(ctx, "Unable to start Temporal worker", "err", err)
		os.Exit(1)
	}
	defer w.Stop()
	logger.InfoContext(ctx, "Temporal Worker started", "queue", "FILE_PROCESSING_TASK_QUEUE")

	startNatsSubscriber(ctx, cfg, c, logger)

	grpcSrv := setupGRPCServer(ctx, cfg, rsaPublicKey, c, logger)
	graphqlSrv := setupGraphQLServer(ctx, cfg, rsaPublicKey, c, logger)

	runServers(ctx, grpcSrv, graphqlSrv, cfg, logger)
}

func initLogger() *slog.Logger {
	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
		ReplaceAttr: func(_ []string, a slog.Attr) slog.Attr {
			if a.Key == slog.TimeKey {
				a.Value = slog.StringValue(a.Value.Time().UTC().Format(time.RFC3339Nano))
			}
			return a
		},
	})
	return slog.New(handler)
}

func initSentry(ctx context.Context, cfg *config.Config, logger *slog.Logger) {
	if cfg.SentryDSN == "" {
		return
	}
	err := sentry.Init(sentry.ClientOptions{
		Dsn:              cfg.SentryDSN,
		Environment:      cfg.Environment,
		Release:          "file-processor@1.0.0",
		TracesSampleRate: 1.0,
	})
	if err != nil {
		logger.ErrorContext(ctx, "Sentry initialization failed", "err", err)
	} else {
		logger.InfoContext(ctx, "Sentry initialized", "environment", cfg.Environment)
	}
}

func connectTemporal(ctx context.Context, cfg *config.Config, logger *slog.Logger) (client.Client, error) {
	// Wave 141 SW5 — Path (a-auth): construct client options ONCE before the
	// retry loop. Includes service token credentials when FP_TEMPORAL_API_KEY_FILE
	// is set (W141 SW4 token minted by start-docker.ps1's
	// New-TemporalServiceToken). Closes W137 §Honesty #5 + W140 NEW #6.
	opts := client.Options{
		HostPort: cfg.TemporalHost,
	}

	if cfg.TemporalAPIKeyFile != "" {
		data, err := os.ReadFile(cfg.TemporalAPIKeyFile)
		if err != nil {
			logger.WarnContext(ctx, "Failed to read Temporal API key file; connecting without auth",
				"path", cfg.TemporalAPIKeyFile,
				"err", err,
			)
		} else {
			token := strings.TrimSpace(string(data))
			if token == "" {
				logger.WarnContext(ctx, "Temporal API key file is empty; connecting without auth",
					"path", cfg.TemporalAPIKeyFile,
				)
			} else {
				// W141 SW5 critical detail: client.NewAPIKeyStaticCredentials AUTO-ENABLES
				// TLS unless ConnectionOptions.TLSDisabled is true (verified at
				// sdk-go/internal/client.go applyToOptions:
				//   if opts.TLS == nil && !opts.TLSDisabled { opts.TLS = &tls.Config{} }
				// ). Our dev compose runs plaintext gRPC at temporal:7233 (no TLS cert
				// in start-docker.ps1 for Temporal Server itself), so we MUST opt out
				// of auto-TLS or Dial fails with TLS handshake error. The Authorization:
				// Bearer <token> header is still attached via the credentials' gRPC
				// interceptor — only the transport-level TLS is bypassed.
				//
				// Production K8s deployments using managed Temporal Cloud will set
				// TLS explicitly (real CA cert) — TLSDisabled stays false there.
				opts.Credentials = client.NewAPIKeyStaticCredentials(token)
				opts.ConnectionOptions = client.ConnectionOptions{
					TLSDisabled: true,
				}
				logger.InfoContext(ctx, "Attached Temporal service token (TLS disabled for plaintext dev gRPC)",
					"path", cfg.TemporalAPIKeyFile,
					"token_chars", len(token),
				)
			}
		}
	} else {
		logger.InfoContext(ctx, "No FP_TEMPORAL_API_KEY_FILE set; connecting to Temporal without auth")
	}

	var c client.Client
	var err error
	maxAttempts := 10
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		c, err = dialTemporalFunc(opts)
		if err == nil {
			logger.InfoContext(ctx, "Connected to Temporal", "addr", cfg.TemporalHost)
			return c, nil
		}
		logger.WarnContext(ctx, "Failed to connect to Temporal, retrying...",
			"attempt", attempt,
			"addr", cfg.TemporalHost,
			"err", err,
		)
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(time.Duration(attempt) * 2 * time.Second):
		}
	}
	return nil, fmt.Errorf("unable to create Temporal client after multiple attempts: %w", err)
}

func setupTemporalWorker(ctx context.Context, c client.Client, cfg *config.Config, logger *slog.Logger) (worker.Worker, *workflow.FileActivities) {
	w := newWorkerFunc(c, "FILE_PROCESSING_TASK_QUEUE", worker.Options{})
	w.RegisterWorkflow(workflow.FileProcessingWorkflow)

	minioClient, err := workflow.BuildMinIOClient(cfg)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to initialize MinIO client", "err", err)
		os.Exit(1)
	}

	activities, err := workflow.NewFileActivities(cfg, minioClient)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to initialize file activities", "err", err)
		os.Exit(1)
	}
	w.RegisterActivity(activities.ResizeImageActivity)

	return w, activities
}

func startNatsSubscriber(ctx context.Context, cfg *config.Config, c client.Client, logger *slog.Logger) {
	var opts []nats.Option
	if cfg.Environment == "testing" {
		opts = append(opts, nats.Timeout(50*time.Millisecond))
	} else {
		opts = append(opts, nats.RetryOnFailedConnect(true), nats.MaxReconnects(-1))
	}

	nc, err := nats.Connect(cfg.NatsURL, opts...)
	if err != nil {
		logger.WarnContext(ctx, "Failed to connect to NATS (Legacy)", "err", err)
		return
	}

	js, err := nc.JetStream()
	if err != nil {
		logger.ErrorContext(ctx, "Failed to get JetStream context", "err", err)
		nc.Close()
		return
	}

	_, err = js.QueueSubscribe("files.process", "file-processors-temporal", func(msg *nats.Msg) {
		var job workflow.ProcessJob
		if err := json.Unmarshal(msg.Data, &job); err != nil {
			logger.ErrorContext(ctx, "Failed to unmarshal NATS message", "err", err)
			if nackErr := msg.Nak(); nackErr != nil {
				logger.ErrorContext(ctx, "Failed to nack NATS message", "err", nackErr)
			}
			return
		}

		opt := client.StartWorkflowOptions{
			ID:                       "proc-" + job.ID + ":" + uuid.NewString(),
			TaskQueue:                "FILE_PROCESSING_TASK_QUEUE",
			WorkflowExecutionTimeout: 30 * time.Minute,
			WorkflowIDReusePolicy:    enumspb.WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE,
		}

		wfCtx, wfCancel := context.WithTimeout(ctx, 5*time.Second)
		defer wfCancel()

		_, execErr := c.ExecuteWorkflow(wfCtx, opt, workflow.FileProcessingWorkflow, job)
		if execErr != nil {
			logger.ErrorContext(ctx, "Failed to execute workflow from NATS", "err", execErr)
			// RZ-W16-02: Nak so JetStream redelivers immediately instead of
			// waiting for AckWait timeout (which can be minutes).
			if nakErr := msg.Nak(); nakErr != nil {
				logger.ErrorContext(ctx, "Failed to Nak NATS message after workflow failure", "err", nakErr)
			}
			return
		}

		if ackErr := msg.Ack(); ackErr != nil {
			logger.ErrorContext(ctx, "Failed to ack NATS message", "err", ackErr)
		}
	}, nats.ManualAck())

	if err != nil {
		logger.ErrorContext(ctx, "Failed to subscribe to NATS queue", "err", err)
	}

	go func() {
		<-ctx.Done()
		nc.Close()
	}()
}

// W140 (z) #2: gRPC health probe (grpc.health.v1.Health) must be exempt
// from auth interceptors. grpc-health-probe binary used in compose-level
// healthcheck (W137 SW5) does not supply bearer tokens, matching the
// standard Kubernetes gRPC health check protocol convention. Pre-W140 the
// healthcheck was unreachable because file-processor never bound the gRPC
// server (schema.graphql + GraphQL ID typing bugs blocked startup at
// step 6), so this auth-blocked-health-probe bug was latent.
const healthMethodPrefix = "/grpc.health.v1.Health/"

func selectiveUnaryAuth(authFn auth.AuthFunc) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req interface{}, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (interface{}, error) {
		if strings.HasPrefix(info.FullMethod, healthMethodPrefix) {
			return handler(ctx, req)
		}
		newCtx, err := authFn(ctx)
		if err != nil {
			return nil, err
		}
		return handler(newCtx, req)
	}
}

func selectiveStreamAuth(authFn auth.AuthFunc) grpc.StreamServerInterceptor {
	return func(srv interface{}, ss grpc.ServerStream, info *grpc.StreamServerInfo, handler grpc.StreamHandler) error {
		if strings.HasPrefix(info.FullMethod, healthMethodPrefix) {
			return handler(srv, ss)
		}
		newCtx, err := authFn(ss.Context())
		if err != nil {
			return err
		}
		wrapped := &authedServerStream{ServerStream: ss, ctx: newCtx}
		return handler(srv, wrapped)
	}
}

type authedServerStream struct {
	grpc.ServerStream
	ctx context.Context
}

func (s *authedServerStream) Context() context.Context { return s.ctx }

func setupGRPCServer(ctx context.Context, cfg *config.Config, rsaPub *rsa.PublicKey, c client.Client, logger *slog.Logger) *grpc.Server {
	authFn := authFunc(cfg.JWTSecret, rsaPub, logger)
	grpcServer := grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
		grpc.ChainStreamInterceptor(
			grpc_prometheus.StreamServerInterceptor,
			selectiveStreamAuth(authFn),
		),
		grpc.ChainUnaryInterceptor(
			grpc_prometheus.UnaryServerInterceptor,
			selectiveUnaryAuth(authFn),
		),
	)

	pb.RegisterFileProcessingServiceServer(grpcServer, &service.Server{TemporalClient: c})
	reflection.Register(grpcServer)
	grpc_prometheus.Register(grpcServer)

	healthServer := health.NewServer()
	grpc_health_v1.RegisterHealthServer(grpcServer, healthServer)
	healthServer.SetServingStatus("", grpc_health_v1.HealthCheckResponse_SERVING)
	healthServer.SetServingStatus("file_processor.v1.FileProcessingService", grpc_health_v1.HealthCheckResponse_SERVING)

	return grpcServer
}

func setupGraphQLServer(ctx context.Context, cfg *config.Config, rsaPub *rsa.PublicKey, c client.Client, logger *slog.Logger) *http.Server {
	s, err := os.ReadFile("schema.graphql")
	if err != nil {
		logger.ErrorContext(ctx, "schema.graphql not found", "err", err)
		os.Exit(1)
	}

	resolver := &gql.Resolver{
		TemporalClient: c,
		MinioBucket:    cfg.MinioBucket,
	}

	var schemaOpts []graphql.SchemaOpt
	// TD-W16-02: Disable introspection in staging too — prevents schema leakage.
	if cfg.Environment == "production" || cfg.Environment == "staging" {
		schemaOpts = append(schemaOpts, graphql.RestrictIntrospection(func(ctx context.Context) bool {
			return false
		}))
	}

	schema := graphql.MustParseSchema(string(s), resolver, schemaOpts...)
	mux := http.NewServeMux()
	graphqlHandler := httpJWTMiddleware(cfg.JWTSecret, rsaPub, logger,
		middleware.MaxQueryDepthMiddleware(10,
			middleware.RequestTimeoutMiddleware(30*time.Second,
				&relay.Handler{Schema: schema},
			),
		),
	)
	mux.Handle("/graphql", graphqlHandler)
	mux.Handle("/metrics", promhttp.Handler())

	return &http.Server{
		Addr:              ":" + cfg.GraphQLPort,
		Handler:           otelhttp.NewHandler(mux, "graphql_metrics"),
		ReadHeaderTimeout: 5 * time.Second,
	}
}

func runServers(ctx context.Context, grpcSrv *grpc.Server, graphqlSrv *http.Server, cfg *config.Config, logger *slog.Logger) {
	lc := net.ListenConfig{}
	lis, err := lc.Listen(ctx, "tcp", ":"+cfg.GRPCPort)
	if err != nil {
		logger.ErrorContext(ctx, "Failed to listen for gRPC", "err", err)
		os.Exit(1)
	}

	go func() {
		logger.InfoContext(ctx, "gRPC Server listening", "addr", ":"+cfg.GRPCPort)
		if err := grpcSrv.Serve(lis); err != nil && !errors.Is(err, grpc.ErrServerStopped) {
			logger.ErrorContext(ctx, "failed to serve gRPC", "err", err)
		}
	}()

	go func() {
		logger.InfoContext(ctx, "GraphQL & Metrics Server listening", "addr", ":"+cfg.GraphQLPort)
		if err := graphqlSrv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.ErrorContext(ctx, "Failed to serve HTTP", "err", err)
		}
	}()

	<-ctx.Done()
	logger.InfoContext(ctx, "Shutting down servers...")

	grpcSrv.GracefulStop()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second) // RZ-33-21: parent ctx is already cancelled
	defer cancel()
	if err := graphqlSrv.Shutdown(shutdownCtx); err != nil { //nolint:contextcheck // RZ-33-21: uses fresh context because parent is cancelled
		logger.ErrorContext(ctx, "HTTP Server forced to shutdown", "err", err)
	}
}

// parseRSAPublicKey parses a PEM-encoded RSA public key.
// TD-W18-01 (audit 2026-03-23 Wave 18): enables RS256 token verification
// for parity with ws-hub and gateway services.
func parseRSAPublicKey(pemStr string) (*rsa.PublicKey, error) {
	block, _ := pem.Decode([]byte(pemStr))
	if block == nil {
		return nil, fmt.Errorf("no PEM block found in RSA_PUBLIC_KEY_PEM")
	}
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("failed to parse RSA public key: %w", err)
	}
	rsaPub, ok := pub.(*rsa.PublicKey)
	if !ok {
		return nil, fmt.Errorf("RSA_PUBLIC_KEY_PEM is not an RSA key (got %T)", pub)
	}
	return rsaPub, nil
}

// jwtKeyFunc returns a jwt.Keyfunc that selects the verification key based on
// the token's signing algorithm.
//
// FIX-ALG-01: When an RSA public key is configured the deployment intends
// RS256-only. Accepting HS256 alongside RS256 would allow an attacker who
// knows (or can guess) the HMAC secret to forge tokens even after an RS256
// key rotation — a classic algorithm-confusion vulnerability. This matches
// the ws-hub behaviour (handlers.go) and the gateway keyFunc (auth.go).
func jwtKeyFunc(secret string, rsaPub *rsa.PublicKey) jwt.Keyfunc {
	return func(t *jwt.Token) (interface{}, error) {
		switch t.Method.(type) {
		case *jwt.SigningMethodRSA:
			if rsaPub == nil {
				return nil, fmt.Errorf("RS256 token received but no RSA public key configured")
			}
			return rsaPub, nil
		case *jwt.SigningMethodHMAC:
			// FIX-ALG-01: Reject HS256 when RS256 is configured — RS256-only deployments
			// must not fall back to HMAC, which would open an algorithm-confusion path.
			if rsaPub != nil {
				return nil, fmt.Errorf("HS256 token rejected: RS256 is configured and HS256 is not accepted alongside it")
			}
			if secret == "" {
				return nil, fmt.Errorf("HS256 token received but no JWT secret configured")
			}
			return []byte(secret), nil
		default:
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
	}
}

func httpJWTMiddleware(secret string, rsaPub *rsa.PublicKey, log *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		const prefix = "Bearer "
		if len(authHeader) <= len(prefix) || authHeader[:len(prefix)] != prefix {
			log.WarnContext(r.Context(), "GraphQL HTTP request missing or malformed Authorization header",
				"remote", r.RemoteAddr,
			)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		tokenStr := authHeader[len(prefix):]

		// FIX-ALG-02: Pre-check the algorithm from the JWT header before calling
		// jwt.Parse. This prevents algorithm-confusion attacks where a crafted token
		// header selects a weaker algorithm (e.g. HS256 when RS256 is expected, or
		// "none"). The check is intentionally done before any cryptographic work so
		// that downgrade attempts are caught and logged immediately.
		// Mirrors the pattern used in gateway/middleware/auth.go (RZ-W15-01).
		if rsaPub != nil {
			parts := strings.SplitN(tokenStr, ".", 3)
			if len(parts) == 3 {
				if headerBytes, decErr := base64.RawURLEncoding.DecodeString(parts[0]); decErr == nil {
					var hdr struct {
						Alg string `json:"alg"`
					}
					if jsonErr := json.Unmarshal(headerBytes, &hdr); jsonErr == nil && hdr.Alg != "RS256" {
						log.WarnContext(r.Context(), "GraphQL HTTP JWT algorithm downgrade attempt rejected",
							"alg", hdr.Alg, "remote", r.RemoteAddr,
							"event", "jwt_alg_downgrade",
						)
						http.Error(w, "Unauthorized", http.StatusUnauthorized)
						return
					}
				}
			}
		}

		// TD-W18-01: use unified keyFunc supporting both RS256 and HS256.
		token, err := jwt.Parse(tokenStr, jwtKeyFunc(secret, rsaPub))
		if err != nil || !token.Valid {
			log.WarnContext(r.Context(), "GraphQL HTTP JWT validation failed",
				"remote", r.RemoteAddr,
				"err", err,
			)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		claims, ok := token.Claims.(jwt.MapClaims)
		if !ok {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		if sub, ok := claims["sub"].(string); ok {
			ctx := context.WithValue(r.Context(), userIDKey, sub)
			r = r.WithContext(ctx)
		}

		next.ServeHTTP(w, r)
	})
}

func authFunc(secret string, rsaPub *rsa.PublicKey, logger *slog.Logger) auth.AuthFunc {
	return func(ctx context.Context) (context.Context, error) {
		tokenStr, err := auth.AuthFromMD(ctx, "bearer")
		if err != nil {
			return nil, err
		}

		// TD-W18-01: use unified keyFunc supporting both RS256 and HS256.
		token, err := jwt.Parse(tokenStr, jwtKeyFunc(secret, rsaPub))

		if err != nil {
			logger.WarnContext(ctx, "gRPC auth failed", "err", err)
			return nil, status.Errorf(codes.Unauthenticated, "invalid token: %v", err)
		}

		if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
			if sub, ok := claims["sub"].(string); ok {
				newCtx := context.WithValue(ctx, userIDKey, sub)
				return newCtx, nil
			}
		}

		return nil, status.Errorf(codes.Unauthenticated, "invalid token claims")
	}
}

func initTracer(ctx context.Context, cfg *config.Config, logger *slog.Logger) (*sdktrace.TracerProvider, error) {
	endpoint := cfg.OTLPEndpoint
	if endpoint == "" {
		endpoint = "jaeger:4317"
	}

	var opts []otlptracegrpc.Option
	opts = append(opts, otlptracegrpc.WithEndpoint(endpoint))

	if cfg.OTLPInsecure {
		if cfg.Environment == "production" {
			return nil, errors.New("OTLP_INSECURE=true is forbidden in production")
		}
		logger.WarnContext(ctx, "OTLP running without TLS — development mode only")
		opts = append(opts, otlptracegrpc.WithInsecure())
	} else {
		opts = append(opts, otlptracegrpc.WithTLSCredentials(credentials.NewTLS(&tls.Config{
			MinVersion: tls.VersionTLS12,
		})))
	}

	exporter, err := otlptracegrpc.New(ctx, opts...)
	if err != nil {
		return nil, err
	}

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("file-processor"),
			attribute.String("environment", cfg.Environment),
		),
	)
	if err != nil {
		return nil, err
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)
	otel.SetTracerProvider(tp)
	// MOD-31-02: Register composite propagator so W3C Baggage headers propagate
	// alongside TraceContext across service boundaries (user_id, request_id).
	otel.SetTextMapPropagator(
		propagation.NewCompositeTextMapPropagator(
			propagation.TraceContext{},
			propagation.Baggage{},
		),
	)
	return tp, nil
}
