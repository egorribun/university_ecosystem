use axum::{
    extract::Json,
    http::StatusCode,
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use tokio::signal;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

const MAX_ITERATIONS: u64 = 500_000_000;

#[tokio::main]
async fn main() {
    tracing_subscriber::registry()
        .with(tracing_subscriber::fmt::layer())
        .init();

    // Initialize Prometheus exporter
    let (prometheus_layer, metric_handle) = axum_prometheus::PrometheusMetricLayer::pair();

    let app = Router::new()
        .route("/health", get(health))
        .route("/optimize", post(optimize))
        .route("/metrics", get(|| async move { metric_handle.render() }))
        .layer(prometheus_layer);

    let addr = SocketAddr::from(([0, 0, 0, 0], 8080));
    tracing::info!("listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .unwrap();
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

#[derive(Deserialize)]
struct OptimizeRequest {
    iterations: u64,
}

#[derive(Serialize)]
struct OptimizeResponse {
    result: u64,
    duration_ms: u128,
}

async fn optimize(Json(payload): Json<OptimizeRequest>) -> Result<Json<OptimizeResponse>, StatusCode> {
    if payload.iterations > MAX_ITERATIONS {
        return Err(StatusCode::BAD_REQUEST);
    }

    let start = std::time::Instant::now();

    // Offload CPU-intensive work to a blocking thread pool
    // This prevents the async runtime from being blocked
    let result = tokio::task::spawn_blocking(move || {
        heavy_computation(payload.iterations)
    })
    .await
    .map_err(|e| {
        tracing::error!("Computation task failed: {}", e);
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    let duration = start.elapsed().as_millis();

    Ok(Json(OptimizeResponse {
        result,
        duration_ms: duration,
    }))
}

// Simulate heavy compute (e.g., recursive fibonacci or similar)
fn heavy_computation(n: u64) -> u64 {
    // Simple verification work: sum of 1..n
    // To make it "heavy", we could do something inefficient.
    // Let's do a loop to simulate CPU work.
    let mut sum = 0;
    for i in 0..n {
        sum += i;
        // Optimization barrier/waste time
        sum = sum.wrapping_mul(2).wrapping_div(2);
    }
    sum
}
