use axum::{
    extract::Json,
    http::StatusCode,
    routing::{get, post},
    Router,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use opentelemetry::KeyValue;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::{runtime, trace as sdktrace, Resource};
use std::env;
use std::net::SocketAddr;
use tokio::signal;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() {
    let sentry_dsn = env::var("SENTRY_DSN").unwrap_or_default();
    let environment = env::var("VITE_ENVIRONMENT").unwrap_or_else(|_| "development".to_string());

    // Initialize Sentry
    let _guard = if !sentry_dsn.is_empty() {
        Some(sentry::init((
            sentry_dsn,
            sentry::ClientOptions {
                release: sentry::release_name!(),
                environment: Some(environment.clone().into()),
                traces_sample_rate: 1.0,
                ..Default::default()
            },
        )))
    } else {
        None
    };

    // Initialize OpenTelemetry
    let tracer = opentelemetry_otlp::new_pipeline()
        .tracing()
        .with_exporter(
            opentelemetry_otlp::new_exporter()
                .tonic()
                .with_endpoint("http://jaeger:4317"),
        )
        .with_trace_config(sdktrace::config().with_resource(Resource::new(vec![
            KeyValue::new("service.name", "rust-optimizer"),
            KeyValue::new("environment", environment),
        ])))
        .install_batch(runtime::Tokio)
        .expect("Failed to initialize OpenTelemetry");

    let opentelemetry_layer = tracing_opentelemetry::layer().with_tracer(tracer);

    tracing_subscriber::registry()
        .with(tracing_subscriber::fmt::layer())
        .with(sentry_tracing::layer())
        .with(opentelemetry_layer)
        .init();

    // Initialize Prometheus exporter
    let (prometheus_layer, metric_handle) = axum_prometheus::PrometheusMetricLayer::pair();

    let app = Router::new()
        .route("/health", get(health))
        .route("/detect-conflicts", post(detect_conflicts))
        .route("/metrics", get(|| async move { metric_handle.render() }))
        .layer(prometheus_layer);

    let addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    tracing::info!("listening on {}", addr);

    let listener = match tokio::net::TcpListener::bind(addr).await {
        Ok(l) => l,
        Err(e) => {
            tracing::error!("failed to bind to {}: {}", addr, e);
            return;
        }
    };

    if let Err(e) = axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
    {
        tracing::error!("server error: {}", e);
    }
}

async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}

async fn health() -> &'static str {
    "OK"
}

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct ScheduleItem {
    pub id: Option<i32>,
    pub weekday: String,
    pub start_time: DateTime<Utc>,
    pub end_time: DateTime<Utc>,
    pub parity: String, // "odd", "even", "both"
}

#[derive(Deserialize)]
struct ConflictRequest {
    target: ScheduleItem,
    existing: Vec<ScheduleItem>,
}

#[derive(Serialize)]
struct ConflictResponse {
    conflicts: Vec<ScheduleItem>,
}

async fn detect_conflicts(
    Json(payload): Json<ConflictRequest>,
) -> Json<ConflictResponse> {
    let target = payload.target;
    let conflicts = payload
        .existing
        .into_iter()
        .filter(|item| has_conflict(&target, item))
        .collect();

    Json(ConflictResponse { conflicts })
}

fn has_conflict(a: &ScheduleItem, b: &ScheduleItem) -> bool {
    // 1. Check weekday
    if a.weekday != b.weekday {
        return false;
    }

    // 2. Check parity overlap
    let parity_conflict = if a.parity == "both" || b.parity == "both" {
        true
    } else {
        a.parity == b.parity
    };

    if !parity_conflict {
        return false;
    }

    // 3. Check time overlap
    // Two intervals [s1, e1] and [s2, e2] overlap if s1 < e2 and s2 < e1
    a.start_time < b.end_time && b.start_time < a.end_time
}
